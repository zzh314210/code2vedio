let csrf = "";
let editJobId = "";
let blankVideoValues = {};
let blankAdvancedConfig = "{}";
let selectedPackConfig = {};
let packRequestSerial = 0;
let projectInputLoading = false;
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
  setValue("course_instructions", course.instructions || ""); setValue("prompt_outline", prompts.outline || ""); setValue("prompt_storyboard", prompts.storyboard || ""); setValue("prompt_code", prompts.code || ""); setValue("prompt_review", prompts.review || "");
}

function patch() {
  if (projectInputLoading) throw Error("项目输入正在载入，请稍后再操作");
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
  if (selectedPackConfig.video) value.video = mergeValues(JSON.parse(JSON.stringify(selectedPackConfig.video)), value.video);
  return mergeValues(value, advanced);
}

async function loadProjectPacks() {
  const result = await api("/api/project-packs");
  $("project_pack").innerHTML = '<option value="">通用空白项目</option>' + result.map(item => '<option value="' + escapeHtml(item.id) + '">' + escapeHtml(item.id) + '</option>').join("");
}
async function selectProjectPack() {
  const name = $("project_pack").value;
  const serial = ++packRequestSerial;
  projectInputLoading = true;
  selectedPackConfig = {};
  $("advanced_config").value = blankAdvancedConfig;
  setValue("course_instructions", "");
  for (const stage of ["outline", "storyboard", "code", "review"]) setValue("prompt_" + stage, "");
  try {
    for (const [id, value] of Object.entries(blankVideoValues)) setValue(id, value);
    const data = name ? (await api("/api/project-packs/" + encodeURIComponent(name))).config : {course:{instructions:"", prompts:{}}};
    if (serial !== packRequestSerial || $("project_pack").value !== name) return;
    selectedPackConfig = name ? data : {};
    const course = data.course || {}, prompts = course.prompts || {}, video = data.video || {};
    setValue("course_instructions", course.instructions || "");
    for (const stage of ["outline", "storyboard", "code", "review"]) setValue("prompt_" + stage, prompts[stage] || "");
    for (const field of ["quality", "font", "max_sections", "max_beats", "fix_attempts"]) {
      const id = ["quality", "font"].includes(field) ? "video_" + field : field;
      setValue(id, video[field] ?? blankVideoValues[id]);
    }
    if (name) $("save_config").checked = false;
  } catch (error) { if (serial === packRequestSerial) { $("project_pack").value = ""; toast(error.message); } }
  finally { if (serial === packRequestSerial) projectInputLoading = false; }
}

async function loadConfig() { const serial = ++packRequestSerial; projectInputLoading = true; try { const data = await api("/api/config"); if (serial !== packRequestSerial) return; selectedPackConfig = {}; renderConfig(data); $("project_pack").value = ""; $("advanced_config").value = blankAdvancedConfig; blankVideoValues = Object.fromEntries(["video_quality", "video_font", "max_sections", "max_beats", "fix_attempts"].map(id => [id, $(id).value])); toast("配置已刷新"); } catch (error) { if (serial === packRequestSerial) toast(error.message); } finally { if (serial === packRequestSerial) projectInputLoading = false; } }
async function saveConfig() { try { const result = await api("/api/config", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); renderConfig(result.config); toast("配置已保存"); } catch (error) { toast(error.message); } }
async function testConfig() { try { const result = await api("/api/config/test", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); toast("测试成功：" + JSON.stringify(result.checks)); } catch (error) { toast("测试失败：" + error.message); } }
async function testTts() { try { const result = await api("/api/tts/test", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); toast("TTS 成功，可试听"); $("tts_preview").src = result.audio_url + "?t=" + Date.now(); $("tts_preview").play().catch(() => {}); } catch (error) { toast(error.message); } }
async function listModels() { try { const result = await api("/api/models", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch())}); toast(result.models.length ? "模型：" + result.models.slice(0, 12).join(", ") : "服务未返回模型列表"); } catch (error) { toast(error.message); } }
async function checkAssets() { try { await saveConfig(); const result = await api("/api/asset-check", {method:"POST"}); $("asset_result").textContent = JSON.stringify(result, null, 2); toast(result.ok ? "图标源检查通过" : "有图标源不可用，请查看结果"); } catch (error) { toast(error.message); } }

async function startJob() {
  try {
    const form = new FormData(); form.append("topic", $("topic").value); form.append("config", JSON.stringify(patch())); form.append("save_config", $("save_config").checked ? "true" : "false"); form.append("stop_after", $("stop_after").value); form.append("allow_generated_code", $("allow_code").checked ? "true" : "false"); form.append("pdf_pages", $("pdf_pages").value); form.append("project_pack", $("project_pack").value);
    for (const file of $("materials").files) form.append("materials", file);
    for (const file of $("resources").files) form.append("resources", file);
    for (const file of $("prompt_templates").files) form.append("prompt_templates", file);
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
  return `<div class="job"><div class="jobhead"><div><b>${escapeHtml(job.topic)}</b><div class="hint">${escapeHtml(job.id)} · ${escapeHtml(job.created_at)}</div><div class="hint" style="word-break:break-all">项目目录：${escapeHtml(job.project_directory || "workspace/" + job.id)}</div></div><span class="badge">${escapeHtml(job.status)}</span></div>${stageHtml(job)}<div>${escapeHtml(job.message || "")} ${result}</div>${job.error ? `<div class="danger">${escapeHtml(job.error)}</div>` : ""}${events}${continueButton}<button class="secondary" onclick="rerun('${escapeHtml(job.id)}')">修改配置后重跑</button><button class="secondary" onclick="loadProject('${escapeHtml(job.id)}')">载入项目配置</button><button class="secondary" onclick="showProjectFiles('${escapeHtml(job.id)}')">项目全部文件</button><button class="secondary" onclick="openEditor('${escapeHtml(job.id)}')">编辑项目提示词/大纲/分镜/代码</button><a href="/api/jobs/${encodeURIComponent(job.id)}/file/output/ATTRIBUTION.md" target="_blank">素材出处</a></div>`;
}
async function pollJobs() { try { const result = await api("/api/jobs"); if ($("jobs").querySelector("video:not([paused])") && [...$("jobs").querySelectorAll("video")].some(video => !video.paused)) return; $("jobs").innerHTML = result.length ? result.sort((first, second) => second.created_at.localeCompare(first.created_at)).map(jobHtml).join("") : '<p class="hint">还没有任务</p>'; } catch (error) { console.warn(error); } }
async function continueJob(id) { try { const result = await api("/api/jobs/" + encodeURIComponent(id) + "/continue", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({stop_after:$("stop_after").value, allow_generated_code:$("allow_code").checked})}); toast("已续跑：" + result.job_id); pollJobs(); } catch (error) { toast(error.message); } }
async function rerun(id) { try { const result = await api("/api/jobs/" + encodeURIComponent(id) + "/rerun", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({topic:$("topic").value || undefined, config:patch(), stop_after:$("stop_after").value, allow_generated_code:$("allow_code").checked, save_config:$("save_config").checked})}); toast("新任务已创建：" + result.job_id); pollJobs(); } catch (error) { toast(error.message); } }


(async function init() { try { csrf = (await api("/api/session")).csrf; await loadConfig(); await loadProjectPacks(); await pollJobs(); setInterval(pollJobs, 2500); } catch (error) { toast(error.message); } })();

function artifactUrl(id, relative) { return `/api/jobs/${encodeURIComponent(id)}/file/` + relative.split("/").map(encodeURIComponent).join("/"); }
function newCourse() {
  ++packRequestSerial;
  projectInputLoading = false;
  selectedPackConfig = {};
  $("project_pack").value = "";
  for (const [id, value] of Object.entries(blankVideoValues)) setValue(id, value);
  for (const name of ["topic", "materials", "resources", "prompt_templates", "pdf_pages", "course_instructions", "prompt_outline", "prompt_storyboard", "prompt_code", "prompt_review"]) $(name).value = "";
  $("advanced_config").value = blankAdvancedConfig;
  toast("新视频输入已清空；模型、语音和素材默认设置保留。每次创建都会生成独立项目目录。");
}
async function loadProject(id) {
  const serial = ++packRequestSerial;
  projectInputLoading = true;
  selectedPackConfig = {};
  $("project_pack").value = "";
  let config;
  try {
    config = await api(`/api/jobs/${encodeURIComponent(id)}/config`);
  } finally {
    if (serial === packRequestSerial) projectInputLoading = false;
  }
  if (serial !== packRequestSerial) return false;
  renderConfig(config);
  function stripSecrets(value) {
    if (Array.isArray(value)) return value.map(stripSecrets);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).filter(([key, item]) => !["api_key", "api_key_configured"].includes(key) && item !== "<redacted>").map(([key, item]) => [key, stripSecrets(item)]));
    return value;
  }
  const advanced = stripSecrets(config);
  delete advanced.course;
  const shown = {text:["protocol","model","base_url"],vision:["enabled","protocol","model","base_url","frames","rounds"],tts:["provider","voice","rate","model","base_url"],video:["quality","font","max_sections","max_beats","fix_attempts"],assets:["enabled","strategy","color"]};
  for (const [role, keys] of Object.entries(shown)) for (const key of keys) delete (advanced[role] || {})[key];
  for (const source of Object.values(advanced.assets?.sources || {})) for (const key of ["enabled","collection","style","providers"]) delete source[key];
  $("advanced_config").value = JSON.stringify(advanced, null, 2);
  for (const name of ["topic", "materials", "resources", "prompt_templates", "pdf_pages"]) if ($(name)) $(name).value = "";
  toast("已载入该项目独立配置；密钥不会回显。更换服务时请提供对应凭证。");
  return true;
}
async function showProjectFiles(id) {
  try {
    const result = await api(`/api/jobs/${encodeURIComponent(id)}/files`);
    $("project_location").textContent = result.project_directory;
    $("project_files").innerHTML = result.files.map(file => `<div><a href="${artifactUrl(id, file.path)}" target="_blank">${escapeHtml(file.path)}</a> <span class="hint">${Math.ceil(file.size / 1024)} KB</span></div>`).join("") || "项目还没有工件";
    $("file_browser").showModal();
  } catch (error) { toast(error.message); }
}
async function openEditor(id) {
  editJobId = id;
  try {
    if (!await loadProject(id)) return;
    const result = await api(`/api/jobs/${encodeURIComponent(id)}/files`);
    const names = result.files.map(file => file.path).filter(path => /^prompts\/(policy|outline|storyboard|code|review)\.txt$/.test(path) || path === "prompts/requirements.json" || /^output\/(outline|storyboard|section_\d+_code)\.json$/.test(path));
    $("edit_file").innerHTML = names.map(filename => `<option value="${escapeHtml(filename)}">${escapeHtml(filename)}</option>`).join("");
    if (!names.length) throw Error("没有可编辑的项目文件");
    await loadArtifact(); $("editor").showModal();
  } catch (error) { toast(error.message); }
}
async function loadArtifact() {
  try {
    const response = await fetch(artifactUrl(editJobId, $("edit_file").value));
    const text = await response.text();
    if (!response.ok) throw Error(text);
    $("edit_data").value = $("edit_file").value.endsWith(".json") ? JSON.stringify(JSON.parse(text), null, 2) : text;
  } catch (error) { toast(error.message); $("edit_data").value = ""; }
}
async function saveEdit() {
  try {
    const name = $("edit_file").value;
    const data = name.endsWith(".json") ? JSON.parse($("edit_data").value) : $("edit_data").value;
    const result = await api(`/api/jobs/${encodeURIComponent(editJobId)}/rerun`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({config:patch(),stop_after:$("stop_after").value,allow_generated_code:$("allow_code").checked,edit_name:name,edit_data:data})});
    $("editor").close(); toast("已创建独立项目新版本：" + result.job_id); pollJobs();
  } catch (error) { toast(error.message); }
}
