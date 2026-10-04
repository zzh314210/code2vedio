import os
from pathlib import Path

from configuration import load_config
from media import sample_frames
from model_gateway import ModelGateway


def cfg(service, key, default=None):
    role = "vision" if service == "gemini" else "text"
    return os.getenv(f"{service}_{key}".upper(), load_config().get(role, {}).get(key, default))


def request_token(prompt, log_id=None, max_tokens=10000, max_retries=3, **kwargs):
    return ModelGateway(load_config()["text"]).request(prompt, max_tokens=max_tokens)


def request_text(prompt, log_id=None, max_tokens=10000, max_retries=3, **kwargs):
    return request_token(prompt, max_tokens=max_tokens)[0]


def request_gemini_with_video(prompt, video_path, log_id=None, max_tokens=10000, max_retries=3):
    settings = load_config()["vision"]
    frames = sample_frames(video_path, Path(video_path).parent / "evaluation_frames", int(settings.get("frames", 6)))
    return ModelGateway(settings, "vision").request(prompt, images=frames, max_tokens=max_tokens)[0]


def request_gemini_video_img(prompt, video_path, image_path=None, log_id=None, max_tokens=10000, max_retries=3):
    settings = load_config()["vision"]
    frames = sample_frames(video_path, Path(video_path).parent / "evaluation_frames", int(settings.get("frames", 6)))
    if image_path:
        frames.append(Path(image_path))
    return ModelGateway(settings, "vision").request(prompt, images=frames, max_tokens=max_tokens)


def request_gpt41_img(prompt, image_path=None, log_id=None, max_tokens=10000, max_retries=3):
    return ModelGateway(load_config()["text"]).request(prompt, images=[image_path] if image_path else None, max_tokens=max_tokens)[0]


request_claude = request_gpt41 = request_gpt5 = request_gpt4o = request_o4mini = request_gemini = request_text
request_claude_token = request_gpt41_token = request_gpt5_token = request_gpt4o_token = request_o4mini_token = request_gemini_token = request_token
request_gemini_video_img_token = request_gemini_video_img
