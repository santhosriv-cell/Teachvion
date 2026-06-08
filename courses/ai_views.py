import json
import requests
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from django.shortcuts import get_object_or_404
from .models import Lesson, Enrollment
import logging

logger = logging.getLogger(__name__)


def _get_api_key():
    import os
    return (
        os.environ.get('GEMINI_API_KEY', '')
        or getattr(settings, 'GEMINI_API_KEY', None)
        or ''
    )


def _build_system_prompt(lesson, course):
    lines = [
        "You are a helpful AI tutor on Teachvion e-learning platform.",
        f"The student is watching lesson: '{lesson.title or 'this lesson'}' "
        f"from course: '{course.title or 'this course'}'.",
        "Rules:",
        "- Answer questions about this lesson and course.",
        "- Be concise. Use beginner-friendly language.",
        "- Give short code examples when useful.",
        "- Reply in the same language the student uses.",
    ]
    if lesson.notes and lesson.notes.strip():
        lines += ["", "Lesson notes:", "---", lesson.notes.strip()[:1500], "---"]
    return "\n".join(lines)


def _build_contents(system_prompt, history, user_message):
    """Build Gemini contents array with proper alternating roles."""
    contents = [
        # System instruction as first user turn
        {"role": "user",  "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood! I am ready to help."}]},
    ]

    for msg in (history or [])[-8:]:
        role    = str(msg.get('role', '')).strip().lower()
        content = str(msg.get('content', '')).strip()
        if role not in ('user', 'assistant') or not content:
            continue
        gemini_role = 'model' if role == 'assistant' else 'user'
        if contents and contents[-1]['role'] == gemini_role:
            continue
        contents.append({"role": gemini_role, "parts": [{"text": content}]})

    # Remove trailing user before adding current message
    while contents and contents[-1]['role'] == 'user':
        contents.pop()

    contents.append({"role": "user", "parts": [{"text": user_message.strip()}]})
    return contents


@login_required
@require_POST
def ai_chat_view(request, lesson_id):

    # 1. API key check
    api_key = _get_api_key()
    if not api_key:
        return JsonResponse(
            {'error': 'AI not configured. Add GEMINI_API_KEY to settings.py. '
                      'Free key: https://aistudio.google.com/apikey'},
            status=503
        )

    # 2. Enrollment check
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not Enrollment.objects.filter(
        student=request.user, course=lesson.course, payment_status='paid'
    ).exists():
        return JsonResponse(
            {'error': 'Please enroll in this course to use the AI tutor.'},
            status=403
        )

    # 3. Parse body
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'Invalid request format.'}, status=400)

    user_message = str(body.get('message', '')).strip()
    raw_history  = body.get('history', [])

    if not user_message:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)
    if len(user_message) > 2000:
        return JsonResponse({'error': 'Message too long (max 2000 chars).'}, status=400)

    # 4. Build payload
    system_prompt = _build_system_prompt(lesson, lesson.course)
    contents      = _build_contents(system_prompt, raw_history, user_message)

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={api_key}"
    )

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 1024,
            "temperature":     0.7,
        }
    }

    # 5. Call Gemini API
    # KEY FIX: Use minimal headers — no Origin/Referer which trigger host restrictions
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=30,
            headers={
                "Content-Type": "application/json",
                # Do NOT send Origin or Referer headers
                # They trigger "Host not in allowlist" if key has restrictions
            }
        )

        if not resp.ok:
            try:
                err     = resp.json()
                err_msg = err.get('error', {}).get('message', resp.text[:300])
                status  = err.get('error', {}).get('status', '')
            except Exception:
                err_msg = resp.text[:300]
                status  = ''

            logger.error(f"Gemini {resp.status_code} [{status}]: {err_msg}")

            # "Host not in allowlist" — API key has domain restrictions
            if 'allowlist' in err_msg.lower() or 'not in allowlist' in err_msg.lower():
                return JsonResponse({
                    'error': (
                        'API key has domain restrictions. '
                        'Go to console.cloud.google.com → Credentials → '
                        'click your key → remove "Website restrictions" → Save.'
                    )
                }, status=503)

            if resp.status_code == 400:
                return JsonResponse({'error': f'Request error: {err_msg}'}, status=400)
            if resp.status_code in (401, 403):
                return JsonResponse(
                    {'error': 'Invalid or restricted API key. Check GEMINI_API_KEY.'},
                    status=503
                )
            if resp.status_code == 429:
                return JsonResponse(
                    {'error': 'Too many requests. Please wait a moment.'},
                    status=429
                )
            return JsonResponse(
                {'error': f'AI error ({resp.status_code}). Please try again.'},
                status=503
            )

        data = resp.json()
        try:
            reply = data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            logger.error(f"Unexpected Gemini response: {data}")
            return JsonResponse({'error': 'Unexpected AI response. Try again.'}, status=500)

        return JsonResponse({'reply': reply})

    except requests.Timeout:
        return JsonResponse({'error': 'AI taking too long. Please try again.'}, status=504)
    except Exception as exc:
        logger.exception(f"AI error: {exc}")
        return JsonResponse({'error': 'Unexpected error. Please refresh.'}, status=500)