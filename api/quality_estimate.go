package main

import "sort"

// Estimates include reasoning output and density-dependent reviews. They are not
// reservations or guarantees. Atomic admission enforces the frozen spending cap.
func qualityEstimate(c PersonalConfig, duration int) (low, high int64, calls int) {
	q := c.Quality
	if q == nil {
		q = defaultQuality()
	}
	sections := max(1, (duration+59)/60)
	beats := sections * 6
	framesPerBeat := int(float64(duration)/float64(beats)/q.SampleSeconds) + 9
	batches := beats * max(1, (framesPerBeat-3+6)/7)
	cost := func(role string, input, output int64) int64 {
		for _, rate := range c.PlatformPrices {
			if rate.Role == role {
				v, e := tokenCost(rate, min(input, rate.MaxInput), output, 0)
				if e == nil {
					return v
				}
			}
		}
		return 0
	}
	base := int64(0)
	possible := []int64{}
	add := func(role string, n, revisions int, input, output int64) {
		unit := cost(role, input, output)
		base += int64(n) * unit
		calls += n
		for i := 0; i < n*(1+revisions); i++ {
			possible = append(possible, cost(role, input*2, output*2))
		}
	}
	add("text", 2, q.Planning, 16000, 16000)
	add("acceptance", 1, q.Planning, 20000, 20000)
	add("text", sections, q.Code+q.Render+q.Visual+q.Final, 18000, 30000)
	add("vision", batches*2, q.Visual+q.Final, 16000, 20000)
	sort.Slice(possible, func(i, j int) bool { return possible[i] > possible[j] })
	maximum := int64(0)
	for i := 0; i < min(len(possible), q.MaxCalls); i++ {
		maximum += possible[i]
	}
	low = ceil(base, 10000)
	high = max(low, ceil(maximum, 10000))
	return
}
