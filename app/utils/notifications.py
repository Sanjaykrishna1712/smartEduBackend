import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

def send_event_notification(event, user_role):
    """Send notifications for calendar events"""
    try:
        print(f"📢 Notification: New event '{event.get('title', 'Event')}' created")
        print(f"   Type: {event.get('type', 'N/A')}")
        print(f"   Date: {event.get('start', 'N/A')}")
        print(f"   Created by: {user_role}")
        
        # You can add actual notification logic here:
        # 1. Email notifications
        # 2. Push notifications
        # 3. In-app notifications
        # 4. SMS notifications
        
        return True
        
    except Exception as e:
        print(f"⚠️ Notification error: {str(e)}")
        return False

def send_email_notification(to_email, subject, message):
    """Send email notification"""
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_username = os.getenv('SMTP_USERNAME', '')
        smtp_password = os.getenv('SMTP_PASSWORD', '')
        
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Email notification failed: {e}")
        return False