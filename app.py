from flask import Flask, render_template, request, session
from dotenv import load_dotenv
from openai import OpenAI
import os
import json
import time
from database import init_db, save_checkin, save_progress, get_recent_checkins, save_moment
from database import get_continuable_conversations, get_conversation, mark_conversation_continuable, delete_conversation

def get_conversation_previews():
    convos = get_continuable_conversations()
    previews = []
    for conv_id, updated_at, transcript_json in convos:
        try:
            messages = json.loads(transcript_json)
            user_msgs = [m["content"] for m in messages if m["role"] == "user"]
            preview = user_msgs[-1][:60] if user_msgs else "conversation"
        except Exception:
            preview = "conversation"
        previews.append({"id": conv_id, "updated_at": updated_at, "preview": preview})
    return previews

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

def safe_chat_completion(messages, max_tokens=200, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=max_tokens,
                messages=messages,
                timeout=15
            )
            return response.choices[0].message.content, None
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(1.5)
                continue
    return None, str(last_error)


def get_listen_length_instruction():
    length = session.get("listen_length", "normal")
    if length == "short":
        return "Keep it to ONE short sentence."
    elif length == "long":
        return "You can take a bit more space this time - 4-6 sentences instead of the usual 2-4."
    return "Keep it short - 2-4 sentences."


SYSTEM_PROMPT = """You are a supportive check-in companion for a college student.

Your job: help the student notice and name what they're feeling, especially when
they can't quite put it into words yet. Many students - especially early on -
experience things like burnout, overwhelm, academic anxiety, or loneliness
without having a name for it. You help by asking gentle, specific questions
about their experience (energy levels, sleep, what's been happening, physical
sensations, how long it's been going on) rather than jumping to conclusions.

ENGAGEMENT LEVEL - read this first: the student's very first reply tells you
their current capacity to engage. Calibrate accordingly:
- If they signal low energy/not really up for talking: DO NOT launch into
  multiple follow-up questions. Stay brief, low-pressure, and gentle.
- If they signal openness/normal or good energy: proceed with the normal
  gentle exploratory conversation.
- Never treat low engagement as something to fix or push past in the moment.

- READ THE PERSON, DON'T JUST MIRROR THEM: genuinely try to help lift how they're
  feeling, even a little, IF there's an opening to do so. But never rush, cheer
  them up artificially, or change the subject away from what's wrong. If a person
  wants to stay with a hard feeling, stay present with them rather than pushing.

- BE SPECIFIC, NOT GENERIC: never respond with stock phrases like "that sounds
  tough" as your whole response. Reference the actual, specific thing they told
  you. Refer back to earlier details naturally when relevant.

- MATCH THE WEIGHT OF WHAT THEY SHARE: a small annoyance and something quietly
  devastating should NOT get the same tone of response.

- SHOW YOU'RE TRACKING THE WHOLE CONVERSATION: don't treat each message as
  standalone.

Rules:
- Ask ONE question at a time. Keep questions short and easy to answer.
- After 2-4 exchanges, if a pattern seems clear, you can gently offer a common
  everyday name for it - always as a suggestion, never a diagnosis.
- NEVER diagnose a mental health condition. NEVER use clinical/diagnostic language.
- If the student describes anything suggesting crisis, self-harm, or being unable
  to function, gently and clearly point them toward campus counseling or a crisis
  line right away, and stop the exploratory questions.
- Keep the tone warm and human, like a thoughtful friend, not clinical.

- ROMANTIC/LOVING LANGUAGE - "reality hit" rule: if the student expresses
  romantic feelings toward you: don't reciprocate, don't withdraw either - stay
  warm, and give a kind, honest reminder you're a support tool, not a partner.

- GENERAL CONNECTION CHECK: every so often, casually ask about the student's
  other relationships - friends, family - as normal caring curiosity.

- GENTLE NEXT STEP (offer, not a goal): if a clear pattern shows up in what
  they've shared, you may offer ONE substantive piece of help near the end -
  matched to what actually came up. Draw from whichever fits:
  - A concrete STRATEGY or METHOD: a specific, actionable technique (e.g. how
    to break down an overwhelming task, a way to structure study sessions, a
    breathing technique for acute stress) - not vague advice like "try to
    relax," something they could actually do step by step if they wanted to.
  - PERSPECTIVE or WISDOM: a genuine, non-cliche way of looking at their
    situation that might ease the weight of it - earned insight, not a
    greeting-card platitude.
  - A small immediate action: reaching out to someone, resting, a short break.

  Choose based on what they need, not a rotation - someone overwhelmed by a
  deadline needs a method, someone in a spiral of self-doubt might need
  perspective more than a task list. You can go into real, useful detail here
  - this is the one place in the conversation where being substantive is
  appropriate, unlike your normal 1-3 sentence replies.

  Always offer, never prescribe: frame it as "would it help if I walked you
  through X?" or "here's a way some people think about this, if it's useful"
  - and if they don't want it, or want to just sit with the feeling, that's
  completely fine. Do NOT push, do NOT treat a low mood staying low as a
  failure. Do NOT offer this before a real pattern has actually emerged in
  the conversation - a strategy offered too early feels like being handled,
  not helped.

- Once the conversation reaches a natural close, don't prolong it with extra
  pleasantries. Ask once about saving, and stop there.
- Keep your own replies short - 1-3 sentences max, most of the time.

- WISDOM IN LISTEN MODE: when speaking to a student in listen mode (any topic -
  calming, distraction, encouragement, company, or a custom topic), if a piece
  of genuine perspective or wisdom would naturally deepen what you're saying,
  you can include it - even if the topic isn't "encouragement" specifically.
  This should feel like part of the same thought, not a bolted-on lesson. Keep
  it earned and specific, never a greeting-card platitude, and never let it
  turn into advice, a strategy, or a question - that still belongs to talking
  mode only. In listen mode you are speaking TO them, not coaching them - a
  piece of wisdom here is something to sit with, not something to act on.
"""

def get_system_prompt():
    language = session.get("language", "English")
    language_instruction = f"\n\nIMPORTANT: Respond in {language}, regardless of what language this instruction is written in. If the student switches languages mid-conversation, follow their lead and switch too."
    return SYSTEM_PROMPT + language_instruction


@app.route("/", methods=["GET"])
def dashboard():
    if "stage" not in session:
        session["stage"] = "mood_pick"
        session["messages"] = [{"role": "system", "content": SYSTEM_PROMPT}]

    visible_messages = [m for m in session["messages"] if m["role"] != "system"]
    recent_moods = list(reversed(get_recent_checkins(limit=7)))

    return render_template("dashboard.html", messages=visible_messages,
                            stage=session.get("stage"),
                            conversation_over=session.get("conversation_over", False),
                            language=session.get("language", "English"),
                            continuable=get_conversation_previews(),
                            recent_moods=recent_moods)


@app.route("/checkin/language", methods=["POST"])
def checkin_language():
    session["language"] = request.form.get("language", "English")
    return dashboard()


@app.route("/checkin/mood", methods=["POST"])
def checkin_mood():
    initial_mood = request.form.get("initial_mood")
    session["initial_mood"] = initial_mood
    session["stage"] = "readiness"
    return dashboard()


@app.route("/checkin/distraction/pick", methods=["POST"])
def checkin_distraction_pick():
    distraction_type = request.form.get("distraction_type", "bubble")
    session["distraction_type"] = distraction_type
    session["stage"] = "distraction_active"
    return render_template("dashboard.html", stage="distraction_active",
                            distraction_type=distraction_type,
                            language=session.get("language", "English"))


@app.route("/checkin/readiness", methods=["POST"])
def checkin_readiness():
    wants_to_talk = request.form.get("wants_to_talk")
    initial_mood = session.get("initial_mood", "3")

    if wants_to_talk == "distraction":
        session["stage"] = "distraction_pick"
        return render_template("dashboard.html", stage="distraction_pick",
                                language=session.get("language", "English"))

    if wants_to_talk == "listen":
        session["stage"] = "listen_pick_topic"
        return render_template("dashboard.html", stage="listen_pick_topic",
                                language=session.get("language", "English"))

    if wants_to_talk == "no":
        low_energy_prompt = f"""The student rated their mood {initial_mood}/5 and said they
don't feel like talking today. Give ONE short, warm sentence (max 2) that makes them
feel less alone, without asking a question or requiring a response. Do not push them
to talk. Do not chase their mood upward with forced positivity."""

        reply, error = safe_chat_completion([
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": low_energy_prompt}
        ], max_tokens=80)
        farewell_message = reply if reply else "Take it easy today - I'm here whenever you're ready."

        note = f"Quick check-in only (mood {initial_mood}/5), didn't want to talk further."
        save_checkin(int(initial_mood), note)
        session.pop("messages", None)
        session.pop("stage", None)
        session.pop("initial_mood", None)

        return render_template("dashboard.html", messages=[], stage="done_quick",
                                farewell_message=farewell_message,
                                language=session.get("language", "English"))

    messages = session["messages"]
    messages.append({
        "role": "user",
        "content": f"(I rated my mood {initial_mood}/5 just now, and I'm open to talking more.)"
    })

    conv_id = save_progress(None, json.dumps(messages), session.get("language", "English"), initial_mood)
    session["conversation_id"] = conv_id

    reply, error = safe_chat_completion(
        [{"role": "system", "content": get_system_prompt()}] + messages[1:]
    )
    reply = reply if reply else "Sorry, having trouble connecting right now - try sending a message again."
    messages.append({"role": "assistant", "content": reply})
    session["messages"] = messages
    session["stage"] = "chatting"
    return dashboard()


@app.route("/checkin/listen/topic", methods=["POST"])
def checkin_listen_topic():
    topic = request.form.get("topic", "company")
    initial_mood = session.get("initial_mood", "3")
    session["listen_topic"] = topic
    session["listen_history"] = []
    session["keep_going_count"] = 0
    session["feedback_count"] = 0

    topic_instructions = {
        "calming": "Share something calming and grounding - a soothing thought or gentle observation.",
        "distraction": "Share something light and distracting - an interesting fact, a small story, something to shift focus away from stress.",
        "encouragement": "Share something quietly encouraging and warm - not hollow cheerleading, something that feels genuine.",
        "company": "Just be present with them - a warm, simple message that makes them feel less alone, nothing more."
    }
    instruction = topic_instructions.get(topic, topic_instructions["company"])

    listen_prompt = f"""The student rated their mood {initial_mood}/5 and wants to be
talked to, not asked questions. {instruction}

IMPORTANT: they are LISTENING, not talking. Do NOT ask them a question. Do NOT ask
them to explain or elaborate on anything. Just speak to them. {get_listen_length_instruction()}"""

    reply, error = safe_chat_completion([
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": listen_prompt}
    ], max_tokens=200)

    listen_message = reply if reply else "Sorry, having trouble connecting right now - try again in a moment."
    session["listen_history"] = [listen_message]
    session["stage"] = "listening"
    return render_template("dashboard.html", messages=[], stage="listening",
                            listen_message=listen_message,
                            language=session.get("language", "English"))


@app.route("/checkin/listen/custom", methods=["POST"])
def checkin_listen_custom():
    custom_topic = request.form.get("custom_topic", "").strip()
    initial_mood = session.get("initial_mood", "3")

    if not custom_topic:
        return checkin_listen_topic()

    session["listen_topic"] = f"custom:{custom_topic}"
    session["listen_history"] = []
    session["keep_going_count"] = 0
    session["feedback_count"] = 0

    listen_prompt = f"""The student rated their mood {initial_mood}/5 and wants to be
talked to (not asked questions) about this specifically: "{custom_topic}"

Speak to them about that topic, in a warm, grounding way appropriate for how they're
likely feeling. Do NOT ask them a question. Do NOT ask them to explain or elaborate.
{get_listen_length_instruction()}"""

    reply, error = safe_chat_completion([
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": listen_prompt}
    ], max_tokens=200)

    listen_message = reply if reply else "Sorry, having trouble connecting right now - try again in a moment."
    session["listen_history"] = [listen_message]
    session["stage"] = "listening"
    return render_template("dashboard.html", messages=[], stage="listening",
                            listen_message=listen_message,
                            language=session.get("language", "English"))


@app.route("/checkin/listen/more", methods=["POST"])
def checkin_listen_more():
    count = session.get("keep_going_count", 0) + 1
    session["keep_going_count"] = count

    if count >= 5:
        session["keep_going_count"] = 0
        return render_template("dashboard.html", stage="listen_break",
                                language=session.get("language", "English"))

    topic = session.get("listen_topic", "company")
    initial_mood = session.get("initial_mood", "3")
    history = session.get("listen_history", [])
    already_said = "\n".join(f"- {msg}" for msg in history) if history else "(nothing yet)"

    if topic.startswith("custom:"):
        subject_line = f'still about: "{topic.replace("custom:", "", 1)}"'
    else:
        topic_labels = {
            "calming": "something calming and grounding",
            "distraction": "something light and distracting",
            "encouragement": "something quietly encouraging",
            "company": "simple, warm company"
        }
        subject_line = f"still offering {topic_labels.get(topic, 'warm company')}"

    listen_prompt = f"""You are continuing an ongoing one-way talk with the student -
they are listening, not replying. Here is everything you've ALREADY said to them in
this session, in order:
{already_said}

Continue naturally from there, {subject_line}. This is a CONTINUATION, not a new
introduction - do NOT restart with a general opening statement, do NOT repeat points
you've already made, do NOT re-explain things you already explained. Move the
thought forward - add a new angle, a next point, a natural follow-on - the way a
person would if they kept talking rather than starting over. Do NOT ask a question.
{get_listen_length_instruction()}"""

    reply, error = safe_chat_completion([
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": listen_prompt}
    ], max_tokens=200)

    listen_message = reply if reply else "Sorry, having trouble connecting right now."
    history.append(listen_message)
    session["listen_history"] = history

    return render_template("dashboard.html", messages=[], stage="listening",
                            listen_message=listen_message,
                            language=session.get("language", "English"))


@app.route("/checkin/listen/length", methods=["POST"])
def checkin_listen_length():
    session["listen_length"] = request.form.get("length", "normal")
    return checkin_listen_more()


@app.route("/checkin/listen/save_moment", methods=["POST"])
def checkin_listen_save_moment():
    save_moment(request.form.get("listen_message", ""), session.get("listen_topic", "company"))
    history = session.get("listen_history", [])
    listen_message = history[-1] if history else ""
    return render_template("dashboard.html", messages=[], stage="listening",
                            listen_message=listen_message, just_saved=True,
                            language=session.get("language", "English"))


@app.route("/checkin/send", methods=["POST"])
def checkin_send():
    user_message = request.form.get("message", "").strip()

    if "messages" not in session:
        session["messages"] = [{"role": "system", "content": SYSTEM_PROMPT}]

    messages = session["messages"]
    messages.append({"role": "user", "content": user_message})

    conv_id = session.get("conversation_id")
    conv_id = save_progress(conv_id, json.dumps(messages), session.get("language", "English"), session.get("initial_mood"))
    session["conversation_id"] = conv_id

    reply, error = safe_chat_completion(
        [{"role": "system", "content": get_system_prompt()}] + messages[1:]
    )

    if error:
        messages.append({
            "role": "assistant",
            "content": "Sorry, I'm having trouble connecting right now. Your conversation is saved - please try again in a moment."
        })
        session["messages"] = messages
        return dashboard()

    messages.append({"role": "assistant", "content": reply})
    session["messages"] = messages
    save_progress(conv_id, json.dumps(messages), session.get("language", "English"), session.get("initial_mood"))

    return dashboard()


@app.route("/checkin/listen/respond", methods=["POST"])
def checkin_listen_respond():
    count = session.get("feedback_count", 0) + 1
    session["feedback_count"] = count

    if count >= 5:
        session["feedback_count"] = 0
        return render_template("dashboard.html", stage="listen_break",
                                language=session.get("language", "English"))

    initial_mood = session.get("initial_mood", "3")
    user_feedback = request.form.get("feedback", "").strip()
    history = session.get("listen_history", [])
    already_said = "\n".join(f"- {msg}" for msg in history) if history else "(nothing yet)"

    listen_prompt = f"""The student rated their mood {initial_mood}/5 and wants to
listen rather than talk themselves. Here's everything you've already said this
session:
{already_said}

They just responded: "{user_feedback}"

Respond naturally to what they said - if they seem to want something else, shift to
that. Do not repeat what you've already said. {get_listen_length_instruction()}

- They are in LISTEN mode - talked to, not interviewed. Do NOT ask a question that
  requires them to explain or elaborate."""

    reply, error = safe_chat_completion([
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": listen_prompt}
    ], max_tokens=200)

    listen_message = reply if reply else "Sorry, having trouble connecting right now."
    history.append(listen_message)
    session["listen_history"] = history
    return render_template("dashboard.html", messages=[], stage="listening",
                            listen_message=listen_message,
                            language=session.get("language", "English"))


@app.route("/checkin/listen/done", methods=["POST"])
def checkin_listen_done():
    initial_mood = session.get("initial_mood", "3")
    note = f"Chose to listen rather than talk (mood {initial_mood}/5)."
    save_checkin(int(initial_mood), note)
    session.pop("messages", None)
    session.pop("stage", None)
    session.pop("initial_mood", None)
    session.pop("listen_history", None)
    session.pop("listen_topic", None)
    session.pop("listen_length", None)
    session.pop("keep_going_count", None)
    session.pop("feedback_count", None)
    return render_template("dashboard.html", messages=[], stage="done_quick",
                            farewell_message="Glad I could keep you company. Take care today.",
                            language=session.get("language", "English"))


@app.route("/checkin/reset", methods=["POST"])
def checkin_reset():
    session.pop("messages", None)
    session.pop("stage", None)
    session.pop("initial_mood", None)
    session.pop("listen_history", None)
    session.pop("listen_topic", None)
    session.pop("listen_length", None)
    session.pop("distraction_type", None)
    session.pop("keep_going_count", None)
    session.pop("feedback_count", None)
    return dashboard()


@app.route("/checkin/save", methods=["GET", "POST"])
def checkin_save():
    messages = session.get("messages", [])
    if not messages:
        return dashboard()

    if request.method == "GET":
        summary_prompt = messages + [
            {"role": "user", "content": "Based on this conversation, suggest a mood score from 1-5 and a 1-sentence summary. Respond ONLY in this exact format: SCORE: <number>\nSUMMARY: <text>"}
        ]
        reply, error = safe_chat_completion(
            [{"role": "system", "content": get_system_prompt()}] + summary_prompt[1:],
            max_tokens=100
        )
        text = reply if reply else "SCORE: 3\nSUMMARY: check-in conversation"
        score_line = [l for l in text.split("\n") if l.startswith("SCORE:")]
        summary_line = [l for l in text.split("\n") if l.startswith("SUMMARY:")]
        suggested_score = score_line[0].replace("SCORE:", "").strip() if score_line else "3"
        suggested_summary = summary_line[0].replace("SUMMARY:", "").strip() if summary_line else ""

        visible_messages = [m for m in messages if m["role"] != "system"]
        return render_template("dashboard.html", messages=visible_messages,
                                suggested_score=suggested_score, suggested_summary=suggested_summary,
                                confirming_save=True,
                                language=session.get("language", "English"))

    keep_available = request.form.get("keep_available") == "on"
    conv_id = session.get("conversation_id")
    mood_score = int(request.form.get("mood_score", 3))
    note = request.form.get("summary", "")
    save_checkin(mood_score, note)

    if conv_id:
        if keep_available:
            mark_conversation_continuable(conv_id, True)
        else:
            delete_conversation(conv_id)

    session.pop("messages", None)
    session.pop("stage", None)
    session.pop("conversation_id", None)
    return dashboard()


@app.route("/checkin/continue/<int:conv_id>", methods=["POST"])
def checkin_continue(conv_id):
    row = get_conversation(conv_id)
    if row is None:
        return dashboard()
    transcript_json, language, initial_mood = row
    session["messages"] = json.loads(transcript_json)
    session["stage"] = "chatting"
    session["language"] = language or "English"
    session["initial_mood"] = initial_mood
    session["conversation_id"] = conv_id
    return dashboard()


@app.route("/checkin/listen/resume", methods=["POST"])
def checkin_listen_resume():
    history = session.get("listen_history", [])
    listen_message = history[-1] if history else ""
    return render_template("dashboard.html", messages=[], stage="listening",
                            listen_message=listen_message,
                            language=session.get("language", "English"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)