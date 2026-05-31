package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"html"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type benchResult struct {
	Name           string           `json:"name"`
	Concurrency    int              `json:"concurrency"`
	Requests       int64            `json:"requests"`
	RequestsPerSec float64          `json:"requests_per_sec"`
	Errors         int64            `json:"errors"`
	LatencyMS      latencySummary   `json:"latency_ms"`
	StatusCounts   map[string]int64 `json:"status_counts"`
}

type latencySummary struct {
	P99 float64 `json:"p99"`
}

type point struct {
	group       string
	concurrency int
	value       float64
}

func main() {
	dir := flag.String("dir", "", "results directory with loadgen JSON files")
	out := flag.String("out", "", "output SVG")
	metric := flag.String("metric", "rps200", "metric: rps200 or p99")
	title := flag.String("title", "", "chart title")
	flag.Parse()

	if *dir == "" || *out == "" {
		fmt.Fprintln(os.Stderr, "-dir and -out are required")
		os.Exit(2)
	}
	points, err := readPoints(*dir, *metric)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read points: %v\n", err)
		os.Exit(1)
	}
	if len(points) == 0 {
		fmt.Fprintln(os.Stderr, "no benchmark JSON files")
		os.Exit(1)
	}
	if *title == "" {
		*title = defaultTitle(*metric)
	}
	if err := os.WriteFile(*out, []byte(renderSVG(*title, *metric, points)), 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write svg: %v\n", err)
		os.Exit(1)
	}
}

func readPoints(dir string, metric string) ([]point, error) {
	files, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		return nil, err
	}
	var points []point
	for _, file := range files {
		raw, err := os.ReadFile(file)
		if err != nil {
			return nil, err
		}
		var result benchResult
		if err := json.Unmarshal(raw, &result); err != nil {
			return nil, fmt.Errorf("%s: %w", file, err)
		}
		group, ok := groupName(result.Name)
		if !ok || result.Concurrency == 0 {
			continue
		}
		value, ok := metricValue(result, metric)
		if !ok {
			continue
		}
		points = append(points, point{
			group:       group,
			concurrency: result.Concurrency,
			value:       value,
		})
	}
	return points, nil
}

func groupName(name string) (string, bool) {
	idx := strings.LastIndex(name, "-c")
	if idx < 0 {
		return "", false
	}
	prefix := name[:idx]
	if _, err := strconv.Atoi(name[idx+2:]); err != nil {
		return "", false
	}
	parts := strings.Split(prefix, "-")
	if len(parts) < 3 {
		return "", false
	}
	proxy := parts[0]
	mode := parts[1]
	if proxy == "tako" && mode == "feature" {
		return strings.ReplaceAll(strings.Join(parts[2:], "-"), "-", " "), true
	}
	endpoint := strings.Join(parts[2:], "-")
	switch proxy {
	case "nginx", "caddy", "tako":
	default:
		return "", false
	}
	switch mode {
	case "single", "lb":
	default:
		return "", false
	}
	label := proxy + " " + mode
	if endpoint != "plaintext" {
		label += " " + endpoint
	}
	return label, true
}

func metricValue(result benchResult, metric string) (float64, bool) {
	switch metric {
	case "rps200":
		if result.Requests <= 0 {
			return 0, false
		}
		okCount := result.StatusCounts["200"]
		return result.RequestsPerSec * float64(okCount) / float64(result.Requests), true
	case "non200pct":
		if result.Requests <= 0 {
			return 0, false
		}
		okCount := result.StatusCounts["200"]
		return 100 * float64(result.Requests-okCount) / float64(result.Requests), true
	case "errorspct":
		total := result.Requests + result.Errors
		if total <= 0 {
			return 0, false
		}
		return 100 * float64(result.Errors) / float64(total), true
	case "p99":
		return result.LatencyMS.P99, true
	default:
		return 0, false
	}
}

func defaultTitle(metric string) string {
	switch metric {
	case "p99":
		return "p99 latency by concurrency"
	case "non200pct":
		return "Non-200 response rate by concurrency"
	case "errorspct":
		return "Client error rate by concurrency"
	default:
		return "HTTP 200 RPS by concurrency"
	}
}

func renderSVG(title string, metric string, points []point) string {
	const (
		width      = 960.0
		height     = 560.0
		left       = 86.0
		right      = 210.0
		top        = 76.0
		bottom     = 78.0
		background = "#101114"
		grid       = "#343843"
		text       = "#d7dae0"
		muted      = "#9ea3ad"
	)

	groups := grouped(points)
	groupNames := sortedGroupNames(groups)
	minX, maxX := xRange(points)
	maxY := niceCeil(maxPoint(points))
	if maxY < 1 {
		maxY = 1
	}

	plotW := width - left - right
	plotH := height - top - bottom
	plotRight := left + plotW

	var b strings.Builder
	fmt.Fprintf(&b, `<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" height="%.0f" viewBox="0 0 %.0f %.0f">`, width, height, width, height)
	fmt.Fprintf(&b, `<rect width="100%%" height="100%%" fill="%s"/>`, background)
	fmt.Fprintf(&b, `<text x="24" y="34" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="18" font-weight="700">%s</text>`, text, html.EscapeString(title))
	fmt.Fprintf(&b, `<text x="24" y="56" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12">%s</text>`, muted, html.EscapeString(metricSubtitle(metric)))

	drawGrid(&b, left, top, plotW, plotH, minX, maxX, maxY, xTicks(points, minX, maxX), grid, muted)

	for _, group := range groupNames {
		pts := groups[group]
		sort.Slice(pts, func(i, j int) bool { return pts[i].concurrency < pts[j].concurrency })
		color := groupColor(group)
		fmt.Fprintf(&b, `<path d="%s" fill="none" stroke="%s" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round"/>`, pathFor(pts, minX, maxX, maxY, left, top, plotW, plotH), color)
		for _, p := range pts {
			x, y := xy(p, minX, maxX, maxY, left, top, plotW, plotH)
			fmt.Fprintf(&b, `<circle cx="%.1f" cy="%.1f" r="3.5" fill="%s"/>`, x, y, color)
		}
	}

	drawLegend(&b, groupNames, plotRight+24, top, text, muted)
	fmt.Fprintf(&b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12" text-anchor="middle">concurrency</text>`, left+plotW/2, height-22, muted)
	fmt.Fprintf(&b, `<text x="20" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12" transform="rotate(-90 20 %.1f)" text-anchor="middle">%s</text>`, top+plotH/2, muted, top+plotH/2, html.EscapeString(yLabel(metric)))
	fmt.Fprint(&b, `</svg>`)
	return b.String()
}

func metricSubtitle(metric string) string {
	switch metric {
	case "p99":
		return "Lower is better. Same HTTPS route, app, certificate, and VM-local load generator."
	case "non200pct":
		return "Lower is better. Share of completed HTTP responses that were not 200."
	case "errorspct":
		return "Lower is better. Client-side/load-generator errors as a share of attempted outcomes."
	default:
		return "Clean throughput only: HTTP 200 responses per second. Same HTTPS route, app, certificate, and VM-local load generator."
	}
}

func yLabel(metric string) string {
	switch metric {
	case "p99":
		return "p99 latency (ms)"
	case "non200pct":
		return "non-200 responses (%)"
	case "errorspct":
		return "client errors (%)"
	default:
		return "HTTP 200 RPS"
	}
}

func grouped(points []point) map[string][]point {
	groups := map[string][]point{}
	for _, p := range points {
		groups[p.group] = append(groups[p.group], p)
	}
	return groups
}

func sortedGroupNames(groups map[string][]point) []string {
	names := make([]string, 0, len(groups))
	for name := range groups {
		names = append(names, name)
	}
	sort.Slice(names, func(i, j int) bool {
		oi := groupOrder(names[i])
		oj := groupOrder(names[j])
		if oi == oj {
			return names[i] < names[j]
		}
		return oi < oj
	})
	return names
}

func groupOrder(name string) int {
	order := map[string]int{
		"nginx single":     1,
		"nginx lb":         2,
		"tako single":      3,
		"tako lb":          4,
		"caddy single":     5,
		"caddy lb":         6,
		"channel publish":  7,
		"workflow enqueue": 8,
	}
	if v, ok := order[name]; ok {
		return v
	}
	return 100
}

func groupColor(name string) string {
	colors := map[string]string{
		"nginx single":     "#4ea1ff",
		"nginx lb":         "#85bfff",
		"tako single":      "#7ee787",
		"tako lb":          "#3fb950",
		"caddy single":     "#f6c177",
		"caddy lb":         "#f0883e",
		"channel publish":  "#7ee787",
		"workflow enqueue": "#f6c177",
	}
	if color, ok := colors[name]; ok {
		return color
	}
	return "#d7dae0"
}

func xRange(points []point) (int, int) {
	minX := points[0].concurrency
	maxX := points[0].concurrency
	for _, p := range points[1:] {
		if p.concurrency < minX {
			minX = p.concurrency
		}
		if p.concurrency > maxX {
			maxX = p.concurrency
		}
	}
	if minX == maxX {
		minX = int(math.Max(0, float64(minX-1)))
		maxX++
	}
	return minX, maxX
}

func maxPoint(points []point) float64 {
	maxY := 0.0
	for _, p := range points {
		if p.value > maxY {
			maxY = p.value
		}
	}
	return maxY
}

func drawGrid(b *strings.Builder, left, top, plotW, plotH float64, minX, maxX int, maxY float64, ticks []int, grid, muted string) {
	plotRight := left + plotW
	plotBottom := top + plotH
	for i := 0; i <= 5; i++ {
		y := top + float64(i)*plotH/5
		value := maxY - float64(i)*maxY/5
		fmt.Fprintf(b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>`, left, y, plotRight, y, grid)
		fmt.Fprintf(b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="11" text-anchor="end">%s</text>`, left-10, y+4, muted, formatNumber(value))
	}
	for _, xValue := range ticks {
		x := left + (float64(xValue-minX)/float64(maxX-minX))*plotW
		fmt.Fprintf(b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>`, x, top, x, plotBottom, grid)
		fmt.Fprintf(b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="11" text-anchor="middle">%d</text>`, x, plotBottom+20, muted, xValue)
	}
}

func xTicks(points []point, minX int, maxX int) []int {
	seen := map[int]bool{}
	var actual []int
	for _, p := range points {
		if !seen[p.concurrency] {
			seen[p.concurrency] = true
			actual = append(actual, p.concurrency)
		}
	}
	sort.Ints(actual)
	if len(actual) <= 8 {
		return actual
	}
	if maxX <= minX {
		return []int{minX}
	}
	stepFloat := niceStep(float64(maxX - minX))
	step := int(math.Ceil(stepFloat))
	if step < 1 {
		step = 1
	}
	start := int(math.Ceil(float64(minX)/float64(step)) * float64(step))
	var ticks []int
	for v := start; v <= maxX; v += step {
		ticks = append(ticks, v)
	}
	if len(ticks) == 0 || ticks[0] != minX {
		ticks = append([]int{minX}, ticks...)
	}
	if ticks[len(ticks)-1] != maxX {
		ticks = append(ticks, maxX)
	}
	return ticks
}

func niceStep(span float64) float64 {
	raw := span / 5
	if raw <= 0 {
		return 1
	}
	pow := math.Pow(10, math.Floor(math.Log10(raw)))
	scaled := raw / pow
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

func pathFor(points []point, minX, maxX int, maxY, left, top, plotW, plotH float64) string {
	var b strings.Builder
	for i, p := range points {
		x, y := xy(p, minX, maxX, maxY, left, top, plotW, plotH)
		if i == 0 {
			fmt.Fprintf(&b, "M %.1f %.1f", x, y)
		} else {
			fmt.Fprintf(&b, " L %.1f %.1f", x, y)
		}
	}
	return b.String()
}

func xy(p point, minX, maxX int, maxY, left, top, plotW, plotH float64) (float64, float64) {
	x := left + (float64(p.concurrency-minX)/float64(maxX-minX))*plotW
	y := top + plotH - (p.value/maxY)*plotH
	return x, y
}

func drawLegend(b *strings.Builder, names []string, x, y float64, text, muted string) {
	fmt.Fprintf(b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12" font-weight="700">series</text>`, x, y, muted)
	for i, name := range names {
		rowY := y + 24 + float64(i)*24
		color := groupColor(name)
		fmt.Fprintf(b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="3" stroke-linecap="round"/>`, x, rowY-4, x+24, rowY-4, color)
		fmt.Fprintf(b, `<text x="%.1f" y="%.1f" fill="%s" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="12">%s</text>`, x+34, rowY, text, html.EscapeString(name))
	}
}

func formatNumber(v float64) string {
	if v >= 1000 {
		return fmt.Sprintf("%.0fk", v/1000)
	}
	if v >= 10 {
		return fmt.Sprintf("%.0f", v)
	}
	return fmt.Sprintf("%.1f", v)
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
