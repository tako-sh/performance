#!/usr/bin/env python3
"""Apply measured changes to an exact copy of pingora-core 0.9.0."""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1])
source = Path(__file__).resolve().parent

def replace(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise SystemExit(f'expected exactly one patch location: {path.name}')
    path.write_text(text.replace(before, after))

l4 = root / 'src/protocols/l4'
shutil.copy(source / 'src/lib.rs', l4 / 'idle_buffer.rs')
shutil.copy(source / 'buffered.rs', l4 / 'buffered.rs')
with (l4 / 'mod.rs').open('a') as f:
    f.write('\nmod buffered;\nmod idle_buffer;\n')
replace(l4 / 'stream.rs',
        'use tokio::io::{self, AsyncRead, AsyncWrite, AsyncWriteExt, BufStream, ReadBuf};',
        'use tokio::io::{self, AsyncRead, AsyncWrite, AsyncWriteExt, ReadBuf};\nuse super::buffered::BufStream;')
replace(l4 / 'stream.rs',
        '    pub(crate) fn set_buffer(&mut self, buffer: L4BufferSettings) {',
        '''    pub(crate) fn set_listener_buffer(&mut self, buffer: L4BufferSettings) {
        static IDLE: std::sync::LazyLock<bool> = std::sync::LazyLock::new(||
            std::env::var("TAKO_BENCH_IDLE_L4").as_deref() == Ok("1"));
        let idle = *IDLE;''')
replace(l4 / 'stream.rs',
        '''            BufStream::with_capacity(
                buffer.read_capacity(),
                buffer.write_capacity(),
                s.into_inner(),
            )''',
        '''            if idle {
                BufStream::with_idle_capacity(buffer.read_capacity(), buffer.write_capacity(), s.into_inner())
            } else {
                BufStream::with_capacity(buffer.read_capacity(), buffer.write_capacity(), s.into_inner())
            }''')
replace(root / 'src/listeners/mod.rs',
        'self.l4.set_buffer(self.l4_buffer);',
        'self.l4.set_listener_buffer(self.l4_buffer);')

h1 = root / 'src/protocols/http/v1'
shutil.copy(source / 'body_release_tests.rs', h1 / 'buffer_release_tests.rs')
with (h1 / 'server.rs').open('a') as f:
    f.write('\n#[cfg(test)]\n#[path = "buffer_release_tests.rs"]\nmod buffer_release_tests;\n')
replace(h1 / 'server.rs',
        '''        let read = self.read_body().await?;
        Ok(read.map(|b| {
            let bytes = Bytes::copy_from_slice(self.get_body(&b));
            self.body_bytes_read += bytes.len();
            if let Some(buffer) = self.retry_buffer.as_mut() {
                buffer.write_to_buffer(&bytes);
            }
            bytes
        }))''',
        '''        static RELEASE_BODY: std::sync::LazyLock<bool> = std::sync::LazyLock::new(||
            std::env::var("TAKO_BENCH_RELEASE_BODY").as_deref() == Ok("1"));
        let read = self.read_body().await?;
        let result = read.map(|b| {
            let bytes = Bytes::copy_from_slice(self.get_body(&b));
            self.body_bytes_read += bytes.len();
            if let Some(buffer) = self.retry_buffer.as_mut() {
                buffer.write_to_buffer(&bytes);
            }
            bytes
        });
        // Returned chunks and retry data own their copies. Pipeline read-ahead
        // has already moved to body_buf_overread and must remain intact.
        if *RELEASE_BODY && self.body_reader.body_done() {
            self.body_reader.body_buf = None;
        }
        Ok(result)''')
