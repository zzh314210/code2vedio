let csrf = "";
let editJobId = "";
const stages = ["outline", "storyboard", "audio", "assets", "code", "render", "review", "compose"];
const labels = {outline:"大纲", storyboard:"分镜", audio:"TTS", assets:"素材", code:"代码", render:"渲染", review:"评审", compose:"合成"};

function $(id) { return document.getElementById(id); }
function toast(message) { const node = $("toast"); node.textContent = message; node.style.display = "block"; setTimeout(() => node.style.display = "none", 4000); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[character])); }
async function api(url, options = {}) {
  const request = {...options, headers: {...(options.headers || {})}};
  if ((request.method || "GET").toUpperCase() !== "GET") request.headers["X-C2V-CSRF"] = csrf;
  const response = await fetch(url, request);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(data.error || response.statusText);
  return data;
}
function setValue(id, value) { if ($(id) && value !== undefined && value !== null) $(id).value = value; }
function setChecked(id, value) { if ($(id)) $(id).checked = Boolean(value); }

function renderConfig(data) {
  const text = data.text || {}, vision = data.vision || {}, tts = data.tts || {}, video = data.video || {}, assets = data.assets || {}, sources = assets.sources || {}, course = data.course || {}, prompts = course.prompts || {};
  setValue("text_protocol", text.protocol); setValue("text_model", text.model); setValue("text_base_url", text.base_url);
  setChecked("vision_enabled", vision.enabled); setValue("vision_protocol", vision.protocol); setValue("vision_model", vision.model); setValue("vision_base_url", vision.base_url); setValue("vision_frames", vision.frames || 6); setValue("vision_rounds", vision.rounds || 1);
  setValue("tts_provider", tts.provider); setValue("tts_voice", tts.voice); setValue("tts_rate", tts.rate); setValue("tts_model", tts.model); setValue("tts_base_url", tts.base_url); $("tts_note").textContent = tts.provider === "edge" ? "Edge TTS 不需要 API Key" : "";
  setValue("video_quality", video.quality); setValue("video_font", video.font); setValue("max_sections", video.max_sections); setValue("max_beats", video.max_beats); setValue("fix_attempts", video.fix_attempts);
  setChecked("assets_enabled", assets.enabled); setValue("assets_strategy", assets.strategy); setValue("assets_color", assets.color); setChecked("asset_iconvaultkit", sources.iconvaultkit?.enabled); setValue("iconvault_collection", sources.iconvaultkit?.collection); setChecked("asset_infyicon", sources.infyicon?.enabled); setValue("infyicon_style", sources.infyicon?.style); setChecked("asset_graphics", sources.graphics_api_remotion?.enabled); setValue("graphics_providers", (sources.graphics_api_remotion?.providers || []).join(","));
  setValue("course_instructions", course.instructions); setValue("prompt_outline", prompts.outline); setValue("prompt_storyboard", prompts.storyboard); setValue("prompt_code", prompts.code); setValue("prompt_review", prompts.review);
}

function patch() {
  const value = {
    text: {protocol: $("text_protocol").value, model: $("text_model").value, base_url: $("text_base_url").value},
    vision: {enabled: $("vision_enabled").checked, protocol: $("vision_protocol").value, model: $("vision_model").value, base_url: $("vision_base_url").value, frames: Number($("vision_frames").value), rounds: Number($("vision_rounds").value)},
    tts: {provider: $("tts_provider").value, voice: $("tts_voice").value, rate: $("tts_rate").value, model: $("tts_model").value, base_url: $("tts_base_url").value},
    video: {quality: $("video_quality").value, font: $("video_font").value, max_sections: Number($("max_sections").value), max_beats: Number($("max_beats").value), fix_attempts: Number($("fix_attempts").value)},
    course: {instructions: $("course_instructions").value, prompts: {outline: $("prompt_outline").value, storyboard: $("prompt_storyboard").value, code: $("prompt_code").value, review: $("prompt_review").value}},
    assets: {enabled: $("assets_enabled").checked, strategy: $("assets_strategy").value, color: $("assets_color").value, sources: {
      iconvaultkit: {enabled: $("asset_iconvaultkit").checked, collection: $("iconvault_collection").value},
      infyicon: {enabled: $("asset_infyicon").checked, style: $("infyicon_style").value},
      graphics_api_remotion: {enabled: $("asset_graphics").checked, providers: $("graphics_providers").value.split(",").map(item => item.trim()).filter(Boolean)}
    }}
  };
  for (const role of ["text", "vision", "tts"]) { const secret = $(role + "_api_key")?.value; if (secret) value[role].api_key = secret; }
  const advanced = JSON.parse($("advanced_config").value || "{}");
  if (!advanced || typeof advanced !== "object" || Array.isArray(advanced)) throw Error("高级配置必须是 JSON 对象");
  function mergeValues(base, updates) { for (const [key, item] of Object.entries(updates)) { if (item && typeof item === "object" && !Array.isArray(item) && base[key] && typeof base[key] === "object") mergeValues(base[key], item); else base[key] = item; } return base; }
  return mergeValues(value, advanced);
}

async function loadConfig() { try { renderConfig(await api("/api/config")); toast("配置已刷新"); } catch (error) { toast(error.message); } }
async function saveConfig() { try { const result = await api("/api/config", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); renderConfig(result.config); toast("配置已保存"); } catch (error) { toast(error.message); } }
async function testConfig() { try { const result = await api("/api/config/test", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); toast("测试成功：" + JSON.stringify(result.checks)); } catch (error) { toast("测试失败：" + error.message); } }
async function testTts() { try { const result = await api("/api/tts/test", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); toast("TTS 成功，可试听"); $("tts_preview").src = result.audio_url + "?t=" + Date.now(); $("tts_preview").play().catch(() => {}); } catch (error) { toast(error.message); } }
async function listModels() { try { const result = await api("/api/models", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); toast(result.models.length ? "模型：" + result.models.slice(0, 12).join(", ") : "服务未返回模型列表"); } catch (error) { toast(error.message); } }
async function checkAssets() { try { await saveConfig(); const result = await api("/api/asset-check", {method:"POST"}); $("asset_result").textContent = JSON.stringify(result, null, 2); toast(result.ok ? "图标源检查通过" : "有图标源不可用，请查看结果"); } catch (error) { toast(error.message); } }

async function startJob() {
  try {
    const form = new FormData(); form.append("topic", $("topic").value); form.append("config", JSON.stringify(patch())); form.append("save_config", $("save_config").checked ? "true" : "false"); form.append("stop_after", $("stop_after").value); form.append("allow_generated_code", $("allow_code").checked ? "true" : "false"); form.append("pdf_pages", $("pdf_pages").value);
    for (const file of $("materials").files) form.append("materials", file);
    const result = await api("/api/jobs", {method:"POST", body:form}); toast("任务已创建：" + result.job_id); $("topic").value = ""; pollJobs();
  } catch (error) { toast(error.message); }
}
function stageHtml(job) {
  return '<div class="stagebar">' + stages.map(stage => { let status = ""; if (job.status === "failed" && stage === job.stage) status = "failed"; else if (job.stage_status === "running" && stage === job.stage) status = "running"; else if ((job.events || []).some(event => event.stage === stage && event.status === "complete")) status = "complete"; return `<div class="stage ${status}">${labels[stage]}</div>`; }).join("") + "</div>";
}
function jobHtml(job) {
  const events = (job.events || []).slice(-8).map(event => `<div class="event">${escapeHtml(event.time)} · <b>${escapeHtml(labels[event.stage] || event.stage)}</b> · ${escapeHtml(event.status)} ${escapeHtml(event.message || "")}</div>`).join("");
  const finalReady = (job.events || []).some(event => event.stage === "compose" && event.status === "complete");
  const result = finalReady ? `<a href="/api/jobs/${encodeURIComponent(job.id)}/file/output/final.mp4" target="_blank">下载最终 MP4</a><video controls preload="none" style="width:100%;max-height:420px;margin-top:12px" src="/api/jobs/${encodeURIComponent(job.id)}/file/output/final.mp4"></video>` : "";
  const continueButton = ["failed", "interrupted", "complete"].includes(job.status) ? `<button class="secondary" onclick="continueJob('${escapeHtml(job.id)}')">继续/从缓存运行</button>` : "";
  return `<div class="job"><div class="jobhead"><div><b>${escapeHtml(job.topic)}</b><div class="hint">${escapeHtml(job.id)} · ${escapeHtml(job.created_at)}</div></div><span class="badge">${escapeHtml(job.status)}</span></div>${stageHtml(job)}<div>${escapeHtml(job.message || "")} ${result}</div>${job.error ? `<div class="danger">${escapeHtml(job.error)}</div>` : ""}${events}${continueButton}<button class="secondary" onclick="rerun('${escapeHtml(job.id)}')">修改配置后重跑</button><button class="secondary" onclick="openEditor('${escapeHtml(job.id)}')">编辑大纲/分镜/代码</button><a href="/api/jobs/${encodeURIComponent(job.id)}/file/output/ATTRIBUTION.md" target="_blank">素材出处</a></div>`;
}
async function pollJobs() { try { const result = await api("/api/jobs"); if ($("jobs").querySelector("video:not([paused])") && [...$("jobs").querySelectorAll("video")].some(video => !video.paused)) return; $("jobs").innerHTML = result.length ? result.sort((first, second) => second.created_at.localeCompare(first.created_at)).map(jobHtml).join("") : '<p class="hint">还没有任务</p>'; } catch (error) { console.warn(error); } }
async function continueJob(id) { try { const result = await api("/api/jobs/" + encodeURIComponent(id) + "/continue", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({stop_after:$("stop_after").value, allow_generated_code:$("allow_code").checked})}); toast("已续跑：" + result.job_id); pollJobs(); } catch (error) { toast(error.message); } }
async function rerun(id) { try { const result = await api("/api/jobs/" + encodeURIComponent(id) + "/rerun", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({topic:$("topic").value || undefined, config:patch(), stop_after:$("stop_after").value, allow_generated_code:$("allow_code").checked, save_config:$("save_config").checked})}); toast("新任务已创建：" + result.job_id); pollJobs(); } catch (error) { toast(error.message); } }

async function openEditor(id) { editJobId = id; try { const outline = await api(`/api/jobs/${encodeURIComponent(id)}/file/output/outline.json`); $("edit_file").innerHTML = ['outline.json','storyboard.json', ...outline.sections.map(section => `${section.id}_code.json`)].map(filename => `<option>${escapeHtml(filename)}</option>`).join(''); await loadArtifact(); $("editor").showModal(); } catch (error) { toast(error.message); } }
async function loadArtifact() { try { const data = await api(`/api/jobs/${encodeURIComponent(editJobId)}/file/output/${encodeURIComponent($("edit_file").value)}`); $("edit_data").value = JSON.stringify(data,null,2); } catch (error) { $("edit_data").value = '{}'; toast(error.message); } }
async function saveEdit() { try { const result = await api(`/api/jobs/${encodeURIComponent(editJobId)}/rerun`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:patch(),stop_after:$("stop_after").value,allow_generated_code:$("allow_code").checked,edit_name:$("edit_file").value,edit_data:JSON.parse($("edit_data").value)})}); $("editor").close();toast('已创建修改版：'+result.job_id);pollJobs(); } catch(error) {toast(error.message);} }

(async function init() { try { csrf = (await api("/api/session")).csrf; await loadConfig(); await pollJobs(); setInterval(pollJobs, 2500); } catch (error) { toast(error.message); } })();
