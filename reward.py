from flask import Blueprint, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import uuid

reward_bp = Blueprint('reward', __name__)

db = SQLAlchemy()

class RewardClaim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer)
    finder_name = db.Column(db.String(100))
    reward_code = db.Column(db.String(50), unique=True)
    reward_type = db.Column(db.String(100))
    is_claimed = db.Column(db.Boolean, default=False)

def generate_reward_code():
    return str(uuid.uuid4())[:8].upper()

@reward_bp.route('/claim_reward/<int:item_id>', methods=['POST'])
def claim_reward(item_id):
    finder_name = request.form.get("finder_name")
    reward_type = request.form.get("reward_type")

    reward_code = generate_reward_code()

    claim = RewardClaim(
        item_id=item_id,
        finder_name=finder_name,
        reward_code=reward_code,
        reward_type=reward_type
    )

    db.session.add(claim)
    db.session.commit()

    return f"Reward claimed! Code: {reward_code}"

@reward_bp.route('/verify_reward/<code>')
def verify_reward(code):
    claim = RewardClaim.query.filter_by(reward_code=code).first()

    if not claim:
        return "Invalid code"

    if claim.is_claimed:
        return "Already claimed"

    claim.is_claimed = True
    db.session.commit()

    return f"Approved: {claim.finder_name} gets {claim.reward_type}"
