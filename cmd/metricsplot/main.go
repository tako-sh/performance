package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"html"
	"math"
	"os"
	"strconv"
	"strings"
	"time"
)

type sample struct {
	t       time.Time
	cpuPct  float64
	memGiB  float64
	conn    float64
	loadOne float64
}

func main() {
	in := flag.String("in", "", "input metrics CSV")
	out := flag.String("out", "", "output SVG")
	title := flag.String("title", "", "chart title")
	summary := flag.String("summary", "", "chart summary")
	flag.Parse()

	if *in == "" || *out == "" {
		fmt.Fprintln(os.Stderr, "-in and -out are required")
		os.Exit(2)
	}
	samples, err := readSamples(*in)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read samples: %v\n", err)
		os.Exit(1)
	}
	if len(samples) == 0 {
		fmt.Fprintln(os.Stderr, "no samples")
		os.Exit(1)
	}
	if *title == "" {
		*title = strings.TrimSuffix(strings.TrimSuffix(*in, "-metrics.csv"), ".csv")
	}
	if err := os.WriteFile(*out, []byte(renderSVG(*title, *summary, samples)), 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write svg: %v\n", err)
		os.Exit(1)
	}
}

func readSamples(path string) ([]sample, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	rows, err := csv.NewReader(file).ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) < 2 {
		return nil, nil
	}
	header := map[string]int{}
	for i, name := range rows[0] {
		header[name] = i
	}

	var samples []sample
	for _, row := range rows[1:] {
		t, err := time.Parse(time.RFC3339, value(row, header, "timestamp"))
		if err != nil {
			continue
		}
		memUsed := parseFloat(value(row, header, "mem_used_bytes"))
		samples = append(samples, sample{
			t:       t,
			cpuPct:  parseFloat(value(row, header, "cpu_pct")),
			memGiB:  memUsed / (1024 * 1024 * 1024),
			conn:    parseFloat(value(row, header, "conn_established")),
			loadOne: parseFloat(value(row, header, "load1")),
		})
	}
	return samples, nil
}

func value(row []string, header map[string]int, name string) string {
	i, ok := header[name]
	if !ok || i >= len(row) {
		return ""
	}
	return row[i]
}

func parseFloat(s string) float64 {
	v, _ := strconv.ParseFloat(strings.TrimSpace(s), 64)
	return v
}

func renderSVG(title string, summary string, samples []sample) string {
	const (
		width      = 960.0
		left       = 70.0
		right      = 28.0
		top        = 82.0
		panelGap   = 58.0
		panelH     = 150.0
		plotWidth  = width - left - right
		cpuTop     = top
		memTop     = top + panelH + panelGap
		connTop    = top + 2*(panelH+panelGap)
		background = "#101114"
		grid       = "#343843"
		text       = "#d7dae0"
		muted      = "#9ea3ad"
		cpuColor   = "#4ea1ff"
		memColor   = "#7ee787"
		connColor  = "#f6c177"
	)

	showConn := maxOf(samples, func(s sample) float64 { return s.conn }) > 0
	height := memTop + panelH + 50
	if showConn {
		height = connTop + panelH + 50
	}
	start := samples[0].t
	end := samples[len(samples)-1].t
	total := end.Sub(start).Seconds()
	if total <= 0 {
		total = 1
	}
	maxCPU := 100.0
	maxMem := niceCeil(maxOf(samples, func(s sample) float64 { return s.memGiB }))
	if maxMem < 1 {
		maxMem = 1
	}
	maxConn := niceCeil(maxOf(samples, func(s sample) float64 { return s.conn }))
	if maxConn < 1 {
		maxConn = 1
	}

	var b strings.Builder
	fmt.Fprintf(&b, `<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" height="%.0f" viewBox="0 0 %.0f %.0f">`, width, height, width, height)
	fmt.Fprintf(&b, `<rect width="100%%" height="100%%" fill="%s"/>`, background)
	fmt.Fprintf(&b, `<text x="24" y="34" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="18" font-weight="700">%s</text>`, text, html.EscapeString(title))
	if summary != "" {
		fmt.Fprintf(&b, `<text x="24" y="54" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12">%s</text>`, muted, html.EscapeString(summary))
	}
	drawPanel(&b, "CPU (% total)", cpuTop, panelH, 0, maxCPU, cpuColor, samples, func(s sample) float64 { return s.cpuPct }, start, total, left, plotWidth, grid, text, muted)
	drawPanel(&b, "Memory used (GiB)", memTop, panelH, 0, maxMem, memColor, samples, func(s sample) float64 { return s.memGiB }, start, total, left, plotWidth, grid, text, muted)
	if showConn {
		drawPanel(&b, "TLS connections", connTop, panelH, 0, maxConn, connColor, samples, func(s sample) float64 { return s.conn }, start, total, left, plotWidth, grid, text, muted)
	}
	fmt.Fprint(&b, `</svg>`)
	return b.String()
}

func drawPanel(
	b *strings.Builder,
	label string,
	yTop float64,
	h float64,
	minY float64,
	maxY float64,
	color string,
	samples []sample,
	get func(sample) float64,
	start time.Time,
	totalSeconds float64,
	left float64,
	plotWidth float64,
	grid string,
	text string,
	muted string,
) {
	right := left + plotWidth
	bottom := yTop + h
	fmt.Fprintf(b, `<text x="24" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="13">%s</text>`, yTop-10, muted, html.EscapeString(label))
	for i := 0; i <= 4; i++ {
		y := yTop + float64(i)*h/4
		value := maxY - float64(i)*(maxY-minY)/4
		fmt.Fprintf(b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>`, left, y, right, y, grid)
		fmt.Fprintf(b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="11" text-anchor="end">%.1f</text>`, left-8, y+4, muted, value)
	}
	for i := 0; i <= 4; i++ {
		x := left + float64(i)*plotWidth/4
		fmt.Fprintf(b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>`, x, yTop, x, bottom, grid)
		fmt.Fprintf(b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="11" text-anchor="middle">%.0fs</text>`, x, bottom+18, muted, float64(i)*totalSeconds/4)
	}
	fmt.Fprintf(b, `<path d="%s" fill="none" stroke="%s" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`, pathFor(samples, get, start, totalSeconds, left, yTop, plotWidth, h, minY, maxY), color)
}

func pathFor(
	samples []sample,
	get func(sample) float64,
	start time.Time,
	totalSeconds float64,
	left float64,
	yTop float64,
	w float64,
	h float64,
	minY float64,
	maxY float64,
) string {
	var b strings.Builder
	for i, s := range samples {
		x := left + (s.t.Sub(start).Seconds()/totalSeconds)*w
		v := get(s)
		if v < minY {
			v = minY
		}
		if v > maxY {
			v = maxY
		}
		y := yTop + h - ((v-minY)/(maxY-minY))*h
		if i == 0 {
			fmt.Fprintf(&b, "M %.1f %.1f", x, y)
		} else {
			fmt.Fprintf(&b, " L %.1f %.1f", x, y)
		}
	}
	return b.String()
}

func maxOf(samples []sample, get func(sample) float64) float64 {
	max := 0.0
	for _, s := range samples {
		if v := get(s); v > max {
			max = v
		}
	}
	return max
}

func niceCeil(v float64) float64 {
	if v <= 0 {
		return 1
	}
	pow := math.Pow(10, math.Floor(math.Log10(v)))
	scaled := v / pow
	switch {
	case scaled <= 1:
		return pow
	case scaled <= 2:
		return 2 * pow
	case scaled <= 5:
		return 5 * pow
	default:
		return 10 * pow
	}
}
