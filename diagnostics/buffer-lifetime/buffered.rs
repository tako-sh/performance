// Keep the exact Tokio implementation as the control in the same binary.
use super::idle_buffer::IdleBufStream;
use std::io::{self, IoSlice};
use std::pin::Pin;
use std::task::{Context, Poll};
use tokio::io::{AsyncRead, AsyncWrite, BufStream as FixedBufStream, ReadBuf};

#[derive(Debug)]
pub(crate) enum BufStream<S> {
    Fixed(FixedBufStream<S>),
    Idle(IdleBufStream<S>),
}
impl<S: AsyncRead + AsyncWrite + Unpin> BufStream<S> {
    pub fn with_capacity(read: usize, write: usize, stream: S) -> Self {
        Self::Fixed(FixedBufStream::with_capacity(read, write, stream))
    }
    pub fn with_idle_capacity(read: usize, write: usize, stream: S) -> Self {
        Self::Idle(IdleBufStream::with_capacity(read, write, stream))
    }
    pub fn get_ref(&self) -> &S {
        match self {
            Self::Fixed(s) => s.get_ref(),
            Self::Idle(s) => s.get_ref(),
        }
    }
    pub fn get_mut(&mut self) -> &mut S {
        match self {
            Self::Fixed(s) => s.get_mut(),
            Self::Idle(s) => s.get_mut(),
        }
    }
    pub fn into_inner(self) -> S {
        match self {
            Self::Fixed(s) => s.into_inner(),
            Self::Idle(s) => s.into_inner(),
        }
    }
}
impl<S: AsyncRead + AsyncWrite + Unpin> AsyncRead for BufStream<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        match self.get_mut() {
            Self::Fixed(s) => Pin::new(s).poll_read(cx, buf),
            Self::Idle(s) => Pin::new(s).poll_read(cx, buf),
        }
    }
}
impl<S: AsyncRead + AsyncWrite + Unpin> AsyncWrite for BufStream<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<io::Result<usize>> {
        match self.get_mut() {
            Self::Fixed(s) => Pin::new(s).poll_write(cx, buf),
            Self::Idle(s) => Pin::new(s).poll_write(cx, buf),
        }
    }
    fn poll_write_vectored(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bufs: &[IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        match self.get_mut() {
            Self::Fixed(s) => Pin::new(s).poll_write_vectored(cx, bufs),
            Self::Idle(s) => Pin::new(s).poll_write_vectored(cx, bufs),
        }
    }
    fn is_write_vectored(&self) -> bool {
        match self {
            Self::Fixed(s) => s.is_write_vectored(),
            Self::Idle(s) => s.is_write_vectored(),
        }
    }
    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        match self.get_mut() {
            Self::Fixed(s) => Pin::new(s).poll_flush(cx),
            Self::Idle(s) => Pin::new(s).poll_flush(cx),
        }
    }
    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        match self.get_mut() {
            Self::Fixed(s) => Pin::new(s).poll_shutdown(cx),
            Self::Idle(s) => Pin::new(s).poll_shutdown(cx),
        }
    }
}
