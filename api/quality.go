package main

import "errors"

// Counts are corrections after the first attempt; zero means inspect once.
type QualityPolicy struct {
	MaxCostCents  int     `json:"max_cost_cents"`
	Planning      int     `json:"planning_revisions"`
	Code          int     `json:"code_revisions"`
	Render        int     `json:"render_revisions"`
	Visual        int     `json:"visual_revisions"`
	Final         int     `json:"final_revisions"`
	MaxCalls      int     `json:"max_model_calls"`
	SampleSeconds float64 `json:"sample_seconds"`
}

func defaultQuality() *QualityPolicy {
	return &QualityPolicy{MaxCostCents: 1000, Planning: 2, Code: 2, Render: 2, Visual: 1, Final: 1, MaxCalls: 60, SampleSeconds: 2}
}
func validateQuality(q *QualityPolicy) error {
	if q == nil {
		return nil
	}
	if q.MaxCostCents < 0 || q.MaxCostCents > 100000 {
		return errors.New("单片平台费用上限需在0至1000元之间，0为不设金额上限。 ")
	}
	for _, n := range []int{q.Planning, q.Code, q.Render, q.Visual, q.Final} {
		if n < 0 || n > 5 {
			return errors.New("各环节最大修改次数需在0至5之间。")
		}
	}
	if q.MaxCalls < 1 || q.MaxCalls > 120 {
		return errors.New("每条视频最多调用模型1至120次。")
	}
	if q.SampleSeconds < 0.5 || q.SampleSeconds > 3 {
		return errors.New("画面验收采样间隔需在0.5至3秒之间。")
	}
	return nil
}
