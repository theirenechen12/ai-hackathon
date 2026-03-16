from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.content_loader import get_topic

router = APIRouter()


class QuizSubmit(BaseModel):
    topic_id: str
    question_id: str
    user_answer: str


@router.post("/quiz/submit")
def submit_quiz(body: QuizSubmit):
    topic = get_topic(body.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    question = next(
        (q for q in topic["trivia_questions"] if q["id"] == body.question_id), None
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    correct = body.user_answer.strip() == question["correct_answer"].strip()

    return {
        "correct": correct,
        "correct_answer": question["correct_answer"],
        "explanation": question["explanation"],
        "sources": question["curated_sources"],
    }
