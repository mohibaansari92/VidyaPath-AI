# models.py
from datetime import datetime
from app import db

class Upload(db.Model):
    __tablename__ = 'uploads'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), index=True, nullable=False)
    stored_filename = db.Column(db.String(1024), nullable=False)
    original_filename = db.Column(db.String(1024))
    content_type = db.Column(db.String(255))
    size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "stored_filename": self.stored_filename,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size": self.size,
            "created_at": self.created_at.isoformat() + "Z"
        }

class QuizResult(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), index=True, nullable=False)
    title = db.Column(db.String(512))
    score = db.Column(db.Float)
    raw_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "score": self.score,
            "raw": self.raw_json,
            "created_at": self.created_at.isoformat() + "Z"
        }
