"""
Email Service for Fantasy Football Assistant

Handles sending verification emails, password reset emails, and other notifications.
Supports both SMTP and development mode.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending notifications and verification emails"""
    
    def __init__(self):
        self.smtp_server = getattr(settings, 'SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_username = getattr(settings, 'SMTP_USERNAME', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
        self.from_email = getattr(settings, 'FROM_EMAIL', 'noreply@fantasyfootball.com')
        self.development_mode = getattr(settings, 'DEVELOPMENT_MODE', True)
    
    async def send_verification_email(self, email: str, verification_token: str) -> bool:
        """Send email verification email"""
        try:
            subject = "Verify Your Fantasy Football Assistant Account"
            
            # Create verification URL
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
            verification_url = f"{frontend_url}/verify-email?token={verification_token}"
            
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #1f2937;">Welcome to Fantasy Football Assistant!</h2>
                    <p>Thank you for creating an account. Please verify your email address by clicking the link below:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verification_url}" 
                           style="background-color: #3b82f6; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 6px; display: inline-block;">
                            Verify Email Address
                        </a>
                    </div>
                    
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p><a href="{verification_url}">{verification_url}</a></p>
                    
                    <p>This link will expire in 24 hours for security purposes.</p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #e5e7eb;">
                    <p style="color: #6b7280; font-size: 14px;">
                        If you didn't create this account, please ignore this email.
                    </p>
                </body>
            </html>
            """
            
            text_content = f"""
            Welcome to Fantasy Football Assistant!
            
            Thank you for creating an account. Please verify your email address by visiting:
            {verification_url}
            
            This link will expire in 24 hours for security purposes.
            
            If you didn't create this account, please ignore this email.
            """
            
            return await self._send_email(email, subject, text_content, html_content)
            
        except Exception as e:
            logger.error(f"Error sending verification email to {email}: {str(e)}")
            return False
    
    async def send_password_reset_email(self, email: str, reset_token: str) -> bool:
        """Send password reset email"""
        try:
            subject = "Reset Your Fantasy Football Assistant Password"
            
            # Create reset URL
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
            reset_url = f"{frontend_url}/reset-password?token={reset_token}"
            
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #1f2937;">Password Reset Request</h2>
                    <p>You've requested to reset your Fantasy Football Assistant password. Click the link below to create a new password:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" 
                           style="background-color: #dc2626; color: white; padding: 12px 24px; 
                                  text-decoration: none; border-radius: 6px; display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p><a href="{reset_url}">{reset_url}</a></p>
                    
                    <p>This link will expire in 1 hour for security purposes.</p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #e5e7eb;">
                    <p style="color: #6b7280; font-size: 14px;">
                        If you didn't request this password reset, please ignore this email. Your password will remain unchanged.
                    </p>
                </body>
            </html>
            """
            
            text_content = f"""
            Password Reset Request
            
            You've requested to reset your Fantasy Football Assistant password. Visit this link to create a new password:
            {reset_url}
            
            This link will expire in 1 hour for security purposes.
            
            If you didn't request this password reset, please ignore this email.
            """
            
            return await self._send_email(email, subject, text_content, html_content)
            
        except Exception as e:
            logger.error(f"Error sending password reset email to {email}: {str(e)}")
            return False
    
    async def _send_email(
        self, 
        to_email: str, 
        subject: str, 
        text_content: str, 
        html_content: Optional[str] = None
    ) -> bool:
        """Send email via SMTP or log in development mode"""
        try:
            if self.development_mode or not self.smtp_username:
                # Development mode - log email instead of sending
                logger.info(f"EMAIL SENT (Dev Mode) - To: {to_email}, Subject: {subject}")
                logger.info(f"Email content:\n{text_content}")
                return True
            
            # Production mode - send via SMTP
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Attach text content
            msg.attach(MIMEText(text_content, 'plain'))
            
            # Attach HTML content if provided
            if html_content:
                msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False


# Global email service instance
email_service = EmailService()


# Helper functions for easy importing
async def send_verification_email(email: str, verification_token: str) -> bool:
    """Send verification email"""
    return await email_service.send_verification_email(email, verification_token)


async def send_password_reset_email(email: str, reset_token: str) -> bool:
    """Send password reset email"""
    return await email_service.send_password_reset_email(email, reset_token)