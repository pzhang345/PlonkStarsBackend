from mail.mail import mail
from flask_mail import Message
from config import Config
from models.feedback import Feedback
from models.db import db
import html
from datetime import datetime, timedelta
import pytz

def send_feedback():
    unsent_feedback = Feedback.query.filter_by(sent=False).all()
    if unsent_feedback == []:
        return
    
    html_body = """
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.5; padding: 20px;">
        <h1 style="color: #4a90e2; text-align: center;">Daily Feedback Report</h1>
    """

    for feedback in unsent_feedback:
        user = feedback.user.username if feedback.user_id else "Anonymous"
        safe_user = html.escape(user)
        safe_timestamp = html.escape(str(feedback.timestamp))
        safe_message = html.escape(feedback.message).replace("\n", "<br>")

        html_body += f"""
        <div style="margin-bottom: 20px; padding: 10px; border-radius: 5px; background-color: #f9f9f9;">
            <p style="margin: 0;"><strong>User:</strong> {safe_user}</p>
            <p style="margin: 0;"><strong>Timestamp:</strong> {safe_timestamp}</p>
            <p style="margin: 0;"><strong>Message:</strong><br>{safe_message}</p>
        </div>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 10px 0;">
        """

        feedback.sent = True

    html_body += """
        <p style="margin-top: 20px; font-size: 0.9em; color: #555; text-align: center;">
            This is an automated email from Plonk Stars Feedback Bot.
        </p>
    </body>
    </html>
    """

    msg = Message(
        subject="Plonk Stars Feedback Summary for " + datetime.now(tz=pytz.utc).strftime("%Y-%m-%d"),
        sender=("Plonk Stars Feedback Bot", Config.MAIL_USERNAME),
        recipients=Config.EMAILS,
        html=html_body
    )

    mail.send(msg)
    db.session.commit()
