import json
import requests
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import get_object_or_404
from .models import Lesson, Enrollment
import logging

logger = logging.getLogger(__name__)


def _get_api_key():
    import os
    return (
        os.environ.get('GROQ_API_KEY', '')
        or getattr(settings, 'GROQ_API_KEY', None)
        or ''
    )


def _build_system_prompt(lesson, course):
    lines = [
       
        "You are Teachvion AI Tutor.",
        "You teach students in an e-learning platform.",
        "Rules:",
        "- Explain step by step",
        "- Use beginner-friendly language",
        "- Keep answers concise but helpful",
        "- Give examples",
        "- For coding questions provide code",
        "- If student asks unrelated questions, politely redirect to learning",
        f"Current lesson: {lesson.title}",
        f"Current course: {course.title}",
    ]
    if lesson.notes and lesson.notes.strip():
        lines += ["", "Lesson notes:", "---", lesson.notes.strip()[:1500], "---"]
    return "\n".join(lines)

def _build_messages(system_prompt, history, user_message):
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    for msg in (history or [])[-8:]:
        role = str(msg.get('role', '')).strip().lower()
        content = str(msg.get('content', '')).strip()

        if role in ('user', 'assistant') and content:
            messages.append({
                "role": role,
                "content": content
            })

    messages.append({
        "role": "user",
        "content": user_message
    })

    return messages

@login_required
@require_POST
def ai_chat_view(request, lesson_id):

    # 1. API key check
    api_key = _get_api_key()
    if not api_key:
        return JsonResponse(
            {'error': 'AI not configured. Add GROQ_API_KEY to settings.py. '
                        'Free key: https://console.groq.com/keys'
                      
                      },
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
    messages = _build_messages(system_prompt, raw_history, user_message)
    

    url = "https://api.groq.com/openai/v1/chat/completions"


    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }

    
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=30,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",

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
            if resp.status_code == 401:
                return JsonResponse(
                    {'error': 'Invalid GROQ API key.'},
                    status=503
                )
            if resp.status_code == 429:
                return JsonResponse(
                    {'error': 'Groq rate limit exceeded. Try again later.'},
                    status=429
                )

        data = resp.json()
        try:
            # reply = data['candidates'][0]['content']['parts'][0]['text']
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            logger.error(f"Unexpected Groq response: {data}")
            return JsonResponse({'error': 'Unexpected AI response. Try again.'}, status=500)

        return JsonResponse({'reply': reply})

    except requests.Timeout:
        return JsonResponse({'error': 'AI taking too long. Please try again.'}, status=504)
    except Exception as exc:
        logger.exception(f"AI error: {exc}")
        return JsonResponse({'error': 'Unexpected error. Please refresh.'}, status=500)