import json
import os
from urllib.parse import urlparse

import frappe
import requests
from google.cloud import storage


def get_gcs_client():
    """
    Get GCS client using credentials from GCS Settings DocType.
    Returns tuple of (client, bucket_name) or None if disabled.
    """
    settings = frappe.get_single("GCS Settings")

    if not settings.enabled:
        return None

    credentials_dict = json.loads(settings.credentials_json)
    client = storage.Client.from_service_account_info(credentials_dict)

    return client, settings.bucket_name


def get_content_type_from_response(response, filename):
    """
    Determine the correct content type from response headers or filename.
    Returns tuple of (content_type, file_extension)
    """
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()

    content_type_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/svg+xml": ".svg",
    }

    ext_to_content_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }

    if content_type in content_type_map:
        return content_type, content_type_map[content_type]

    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in ext_to_content_type:
            return ext_to_content_type[ext], ext

    return "image/jpeg", ".jpg"


def upload_image_to_gcs(img_url, submission_name):
    """
    Download image from external URL and upload to GCS.
    Returns the public URL.
    """
    try:
        result = get_gcs_client()

        if result is None:
            frappe.throw("GCS Storage is not enabled. Enable it in GCS Settings.")

        client, bucket_name = result

        response = requests.get(img_url, timeout=30)
        response.raise_for_status()

        parsed_url = urlparse(img_url)
        original_filename = os.path.basename(parsed_url.path)
        content_type, ext = get_content_type_from_response(response, original_filename)

        if not original_filename or "." not in original_filename:
            original_filename = f"image{ext}"

        gcs_filename = f"submissions/{submission_name}_{original_filename}"

        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_filename)
        blob.upload_from_string(response.content, content_type=content_type)

        public_url = f"https://storage.googleapis.com/{bucket_name}/{gcs_filename}"

        frappe.logger("submission").info(
            f"Image uploaded to GCS: {img_url} -> {public_url} (content_type: {content_type})"
        )

        return public_url

    except requests.exceptions.RequestException as e:
        frappe.logger("submission").error(f"Failed to download image from {img_url}: {str(e)}")
        raise frappe.ValidationError(f"Failed to download image: {str(e)}")
    except Exception as e:
        frappe.logger("submission").error(f"Failed to upload to GCS: {str(e)}")
        raise frappe.ValidationError(f"Failed to upload to GCS: {str(e)}")


def upload_audio_to_gcs(local_audio_path: str, submission_id: str, original_filename: str) -> str:
    """
    Upload audio file from local path to GCS.
    Returns the public URL.
    """
    try:
        result = get_gcs_client()

        if result is None:
            frappe.throw("GCS Storage is not enabled. Enable it in GCS Settings.")

        client, bucket_name = result

        if not os.path.exists(local_audio_path):
            raise FileNotFoundError(f"Audio file not found at {local_audio_path}")

        ext = os.path.splitext(original_filename)[1].lower()
        content_type_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
        }
        content_type = content_type_map.get(ext, "audio/mpeg")

        gcs_filename = f"audio_feedback/{submission_id}_{original_filename}"

        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_filename)

        with open(local_audio_path, "rb") as f:
            blob.upload_from_file(f, content_type=content_type)

        public_url = f"https://storage.googleapis.com/{bucket_name}/{gcs_filename}"

        frappe.logger("submission").info(
            f"Audio uploaded to GCS: {local_audio_path} -> {public_url} (content_type: {content_type})"
        )

        return public_url

    except FileNotFoundError as e:
        frappe.logger("submission").error(f"Audio file not found: {str(e)}")
        raise frappe.ValidationError(f"Audio file not found: {str(e)}")
    except Exception as e:
        frappe.logger("submission").error(f"Failed to upload audio to GCS: {str(e)}")
        raise frappe.ValidationError(f"Failed to upload audio to GCS: {str(e)}")


def upload_video_to_gcs(video_url: str, submission_id: str) -> str:
    """
    Download video from external URL and upload to GCS.
    Returns the public URL.
    """
    try:
        result = get_gcs_client()
        if result is None:
            frappe.throw("GCS Storage is not enabled. Enable it in GCS Settings.")
        client, bucket_name = result

        response = requests.get(video_url, timeout=60, stream=True)
        response.raise_for_status()

        parsed_url = urlparse(video_url)
        original_filename = os.path.basename(parsed_url.path)

        content_type_map = {
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "video/x-msvideo": ".avi",
            "video/x-matroska": ".mkv",
            "video/webm": ".webm",
            "video/x-flv": ".flv",
            "video/x-ms-wmv": ".wmv",
        }
        ext_to_content_type = {v: k for k, v in content_type_map.items()}

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        ext = content_type_map.get(content_type)

        if not ext and original_filename:
            ext = os.path.splitext(original_filename)[1].lower()
            content_type = ext_to_content_type.get(ext, "video/mp4")
        if not ext:
            ext = ".mp4"
            content_type = "video/mp4"

        if not original_filename or "." not in original_filename:
            original_filename = f"video{ext}"

        gcs_filename = f"submissions/{submission_id}_{original_filename}"

        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_filename)
        blob.upload_from_string(response.content, content_type=content_type)

        public_url = f"https://storage.googleapis.com/{bucket_name}/{gcs_filename}"

        frappe.logger("submission").info(
            f"Video uploaded to GCS: {video_url} -> {public_url} (content_type: {content_type})"
        )

        return public_url

    except requests.exceptions.RequestException as e:
        frappe.logger("submission").error(f"Failed to download video from {video_url}: {str(e)}")
        raise frappe.ValidationError(f"Failed to download video: {str(e)}")
    except Exception as e:
        frappe.logger("submission").error(f"Failed to upload video to GCS: {str(e)}")
        raise frappe.ValidationError(f"Failed to upload video to GCS: {str(e)}")


def upload_to_gcs(submission_url, submission_name):
    """
    Detect media type (image or video) from the URL extension and upload to GCS.
    Returns the public URL.
    """
    image_exts = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}
    video_exts = {"mp4", "mov", "avi", "mkv", "webm", "flv", "wmv"}

    url_without_query = submission_url.split("?", 1)[0].lower()
    if "." in url_without_query:
        ext = url_without_query.rsplit(".", 1)[-1]
        if ext in image_exts:
            return upload_image_to_gcs(submission_url, submission_name)
        if ext in video_exts:
            return upload_video_to_gcs(submission_url, submission_name)

    return upload_image_to_gcs(submission_url, submission_name)
