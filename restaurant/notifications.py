"""
Notification system for restaurant bookings - Email, SMS, and calendar integration
Better than OpenTable/Resy with personalization and multi-channel delivery
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dotenv import load_dotenv
import icalendar
import base64

load_dotenv()

class RestaurantNotificationService:
    """Comprehensive notification service for restaurant bookings"""

    def __init__(self):
        # Email configuration
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", "reservations@bellavista.com")

        # SMS configuration (Twilio)
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")

        # Restaurant info
        self.restaurant_name = "Bella Vista"
        self.restaurant_address = "123 Italian Way, New York, NY 10001"
        self.restaurant_phone = "(929) 592-5370"
        self.restaurant_website = "https://bellavista.com"

        print("🍽️ Restaurant notification service initialized")

    def send_booking_confirmation(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send comprehensive booking confirmation via email and SMS"""
        results = {
            'email_sent': False,
            'sms_sent': False,
            'calendar_attached': False,
            'errors': []
        }

        try:
            # Send email confirmation
            email_result = self._send_confirmation_email(booking_data)
            results['email_sent'] = email_result['success']
            if not email_result['success']:
                results['errors'].append(f"Email error: {email_result['error']}")

            # Send SMS confirmation
            sms_result = self._send_confirmation_sms(booking_data)
            results['sms_sent'] = sms_result['success']
            if not sms_result['success']:
                results['errors'].append(f"SMS error: {sms_result['error']}")

            results['calendar_attached'] = email_result.get('calendar_attached', False)

        except Exception as e:
            results['errors'].append(f"Notification error: {str(e)}")

        return results

    def send_booking_reminder(self, booking_data: Dict[str, Any], hours_before: int = 24) -> Dict[str, Any]:
        """Send booking reminder via email and SMS"""
        results = {
            'email_sent': False,
            'sms_sent': False,
            'errors': []
        }

        try:
            # Send email reminder
            email_result = self._send_reminder_email(booking_data, hours_before)
            results['email_sent'] = email_result['success']
            if not email_result['success']:
                results['errors'].append(f"Email error: {email_result['error']}")

            # Send SMS reminder
            sms_result = self._send_reminder_sms(booking_data, hours_before)
            results['sms_sent'] = sms_result['success']
            if not sms_result['success']:
                results['errors'].append(f"SMS error: {sms_result['error']}")

        except Exception as e:
            results['errors'].append(f"Reminder error: {str(e)}")

        return results

    def send_booking_update(self, booking_data: Dict[str, Any], change_type: str) -> Dict[str, Any]:
        """Send booking update notification (modification/cancellation)"""
        results = {
            'email_sent': False,
            'sms_sent': False,
            'errors': []
        }

        try:
            # Send email update
            email_result = self._send_update_email(booking_data, change_type)
            results['email_sent'] = email_result['success']
            if not email_result['success']:
                results['errors'].append(f"Email error: {email_result['error']}")

            # Send SMS update
            sms_result = self._send_update_sms(booking_data, change_type)
            results['sms_sent'] = sms_result['success']
            if not sms_result['success']:
                results['errors'].append(f"SMS error: {sms_result['error']}")

        except Exception as e:
            results['errors'].append(f"Update error: {str(e)}")

        return results

    def _send_confirmation_email(self, booking: Dict[str, Any]) -> Dict[str, Any]:
        """Send beautiful HTML email confirmation with calendar attachment"""
        try:
            guest_email = booking.get('guest_email', f"{booking.get('guest_name', 'Guest').replace(' ', '').lower()}@example.com")

            # Create calendar attachment
            calendar_ics = self._generate_calendar_invite(booking)

            # Create HTML email
            html_content = self._get_confirmation_email_html(booking)
            text_content = self._get_confirmation_email_text(booking)

            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🎉 Your Bella Vista Reservation Confirmed!"
            msg['From'] = f"Bella Vista <{self.from_email}>"
            msg['To'] = guest_email

            # Attach text version
            text_part = MIMEText(text_content, 'plain')
            msg.attach(text_part)

            # Attach HTML version
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Attach calendar invite
            if calendar_ics:
                calendar_part = MIMEBase('text', 'calendar', method='REQUEST', name='reservation.ics')
                calendar_part.set_payload(calendar_ics)
                encoders.encode_base64(calendar_part)
                calendar_part.add_header('Content-Disposition', 'attachment', filename='bella_vista_reservation.ics')
                calendar_part.add_header('Content-class', 'urn:content-classes:calendarmessage')
                msg.attach(calendar_part)

            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()

            return {
                'success': True,
                'calendar_attached': calendar_ics is not None
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _send_confirmation_sms(self, booking: Dict[str, Any]) -> Dict[str, Any]:
        """Send SMS confirmation via Twilio"""
        try:
            if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]):
                return {'success': False, 'error': 'Twilio not configured'}

            phone = booking.get('phone', '')
            if not phone:
                return {'success': False, 'error': 'No phone number provided'}

            message = self._get_confirmation_sms_text(booking)

            # Using Twilio API
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
            auth = (self.twilio_account_sid, self.twilio_auth_token)
            data = {
                'From': self.twilio_phone_number,
                'To': phone,
                'Body': message
            }

            response = requests.post(url, auth=auth, data=data)

            if response.status_code == 201:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Twilio error: {response.text}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _send_reminder_email(self, booking: Dict[str, Any], hours_before: int) -> Dict[str, Any]:
        """Send reminder email"""
        try:
            guest_email = booking.get('guest_email', f"{booking.get('guest_name', 'Guest').replace(' ', '').lower()}@example.com")

            html_content = self._get_reminder_email_html(booking, hours_before)
            text_content = self._get_reminder_email_text(booking, hours_before)

            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🔔 Bella Vista Reminder - {hours_before} Hours Until Your Reservation"
            msg['From'] = f"Bella Vista <{self.from_email}>"
            msg['To'] = guest_email

            text_part = MIMEText(text_content, 'plain')
            msg.attach(text_part)

            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()

            return {'success': True}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _send_reminder_sms(self, booking: Dict[str, Any], hours_before: int) -> Dict[str, Any]:
        """Send SMS reminder via Twilio"""
        try:
            if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]):
                return {'success': False, 'error': 'Twilio not configured'}

            phone = booking.get('phone', '')
            if not phone:
                return {'success': False, 'error': 'No phone number provided'}

            message = self._get_reminder_sms_text(booking, hours_before)

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
            auth = (self.twilio_account_sid, self.twilio_auth_token)
            data = {
                'From': self.twilio_phone_number,
                'To': phone,
                'Body': message
            }

            response = requests.post(url, auth=auth, data=data)

            if response.status_code == 201:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Twilio error: {response.text}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _send_update_email(self, booking: Dict[str, Any], change_type: str) -> Dict[str, Any]:
        """Send booking update email"""
        try:
            guest_email = booking.get('guest_email', f"{booking.get('guest_name', 'Guest').replace(' ', '').lower()}@example.com")

            html_content = self._get_update_email_html(booking, change_type)
            text_content = self._get_update_email_text(booking, change_type)

            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"📝 Bella Vista Reservation {change_type.title()}"
            msg['From'] = f"Bella Vista <{self.from_email}>"
            msg['To'] = guest_email

            text_part = MIMEText(text_content, 'plain')
            msg.attach(text_part)

            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()

            return {'success': True}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _send_update_sms(self, booking: Dict[str, Any], change_type: str) -> Dict[str, Any]:
        """Send SMS update via Twilio"""
        try:
            if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]):
                return {'success': False, 'error': 'Twilio not configured'}

            phone = booking.get('phone', '')
            if not phone:
                return {'success': False, 'error': 'No phone number provided'}

            message = self._get_update_sms_text(booking, change_type)

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
            auth = (self.twilio_account_sid, self.twilio_auth_token)
            data = {
                'From': self.twilio_phone_number,
                'To': phone,
                'Body': message
            }

            response = requests.post(url, auth=auth, data=data)

            if response.status_code == 201:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Twilio error: {response.text}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _generate_calendar_invite(self, booking: Dict[str, Any]) -> Optional[str]:
        """Generate iCalendar (.ics) file for calendar integration"""
        try:
            cal = icalendar.Calendar()
            cal.add('prodid', '-//Bella Vista Reservation//')
            cal.add('version', '2.0')

            event = icalendar.Event()
            event.add('summary', f'Bella Vista Reservation - {booking.get("guest_name", "Guest")}')
            event.add('description', f'Dinner reservation for {booking.get("party_size", 1)} people at Bella Vista')
            event.add('location', self.restaurant_address)

            # Parse date and time
            booking_date = booking.get('date', '')
            booking_time = booking.get('time', '')

            if booking_date and booking_time:
                start_datetime = datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
                end_datetime = start_datetime + timedelta(hours=2)  # Assume 2-hour reservation

                event.add('dtstart', start_datetime)
                event.add('dtend', end_datetime)

                # Add reminder
                alarm = icalendar.Alarm()
                alarm.add('action', 'DISPLAY')
                alarm.add('description', 'Bella Vista Reservation Reminder')
                alarm.add('trigger', timedelta(hours=-2))  # 2 hours before
                event.add_component(alarm)

                cal.add_component(event)

                return cal.to_ical().decode('utf-8')

        except Exception as e:
            print(f"Calendar generation error: {e}")
            return None

    def _get_confirmation_email_html(self, booking: Dict[str, Any]) -> str:
        """Generate beautiful HTML email confirmation"""
        booking_date = booking.get('date', '')
        booking_time = booking.get('time', '')
        guest_name = booking.get('guest_name', 'Valued Guest')

        # Format date nicely
        try:
            date_obj = datetime.strptime(booking_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%A, %B %d, %Y')
        except:
            formatted_date = booking_date

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Your Bella Vista Reservation</title>
        </head>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f8f9fa;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center; color: white;">
                    <h1 style="margin: 0; font-size: 28px; font-weight: 300;">🎉 Reservation Confirmed!</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Thank you for choosing Bella Vista</p>
                </div>

                <!-- Content -->
                <div style="padding: 40px 30px;">
                    <h2 style="color: #333; margin-bottom: 30px; font-size: 24px;">Dear {guest_name},</h2>

                    <p style="font-size: 16px; line-height: 1.6; color: #555; margin-bottom: 30px;">
                        We're delighted to confirm your reservation at <strong>Bella Vista</strong>, where authentic Italian meets modern elegance.
                    </p>

                    <!-- Reservation Details -->
                    <div style="background: #f8f9fa; border-radius: 8px; padding: 25px; margin-bottom: 30px;">
                        <h3 style="margin-top: 0; color: #333; font-size: 20px;">📅 Reservation Details</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Date:</strong></td>
                                <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{formatted_date}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Time:</strong></td>
                                <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{booking_time}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Party Size:</strong></td>
                                <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{booking.get('party_size', 1)} guests</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0;"><strong>Reservation:</strong></td>
                                <td style="padding: 8px 0;">{booking.get('id', 'Confirmed')}</td>
                            </tr>
                        </table>
                    </div>

                    <!-- Restaurant Info -->
                    <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; border-radius: 8px; padding: 25px; margin-bottom: 30px;">
                        <h3 style="margin-top: 0; font-size: 20px;">🏛️ Bella Vista</h3>
                        <p style="margin: 0; line-height: 1.6;">
                            <strong>Address:</strong> {self.restaurant_address}<br>
                            <strong>Phone:</strong> {self.restaurant_phone}<br>
                            <strong>Website:</strong> <a href="{self.restaurant_website}" style="color: white; text-decoration: underline;">{self.restaurant_website}</a>
                        </p>
                    </div>

                    <!-- Special Instructions -->
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 20px; margin-bottom: 30px;">
                        <h4 style="margin-top: 0; color: #856404;">💡 Important Information</h4>
                        <ul style="margin: 0; padding-left: 20px; color: #856404;">
                            <li>Please arrive 10-15 minutes before your reservation time</li>
                            <li>We'll hold your table for 15 minutes past your reservation time</li>
                            <li>For parties of 6 or more, please call to confirm availability</li>
                            <li>Casual elegant attire recommended</li>
                        </ul>
                    </div>

                    <!-- Calendar Integration -->
                    <div style="text-align: center; margin-bottom: 30px;">
                        <p style="color: #666; margin-bottom: 15px;">📱 <strong>Add to Calendar</strong></p>
                        <p style="font-size: 14px; color: #888;">A calendar invite has been attached to this email</p>
                    </div>

                    <!-- Contact -->
                    <div style="text-align: center; padding-top: 30px; border-top: 1px solid #eee;">
                        <p style="color: #666; margin-bottom: 10px;">Questions about your reservation?</p>
                        <p style="margin: 0;">
                            <strong>Call us:</strong> {self.restaurant_phone}<br>
                            <strong>Email:</strong> reservations@bellavista.com
                        </p>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background: #f8f9fa; padding: 20px 30px; text-align: center; color: #666; font-size: 14px;">
                    <p style="margin: 0;">
                        Bella Vista | Authentic Italian Dining<br>
                        123 Italian Way, New York, NY 10001
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_confirmation_email_text(self, booking: Dict[str, Any]) -> str:
        """Generate text version of confirmation email"""
        return f"""
        BELLA VISTA RESERVATION CONFIRMED
        ==================================

        Dear {booking.get('guest_name', 'Valued Guest')},

        We're delighted to confirm your reservation at Bella Vista!

        RESERVATION DETAILS:
        Date: {booking.get('date', '')}
        Time: {booking.get('time', '')}
        Party Size: {booking.get('party_size', 1)} guests
        Reservation ID: {booking.get('id', 'Confirmed')}

        RESTAURANT INFORMATION:
        Bella Vista
        {self.restaurant_address}
        Phone: {self.restaurant_phone}
        Website: {self.restaurant_website}

        IMPORTANT INFORMATION:
        - Please arrive 10-15 minutes before your reservation time
        - We'll hold your table for 15 minutes past your reservation time
        - For parties of 6 or more, please call to confirm availability
        - Casual elegant attire recommended

        Questions? Call us at {self.restaurant_phone}

        Thank you for choosing Bella Vista!
        """

    def _get_confirmation_sms_text(self, booking: Dict[str, Any]) -> str:
        """Generate SMS confirmation text"""
        return f"""🎉 Confirmed! Bella Vista reservation for {booking.get('party_size', 1)} on {booking.get('date', '')} at {booking.get('time', '')}. See you soon! 🍽️"""

    def _get_reminder_email_html(self, booking: Dict[str, Any], hours_before: int) -> str:
        """Generate reminder email HTML"""
        booking_date = booking.get('date', '')
        booking_time = booking.get('time', '')
        guest_name = booking.get('guest_name', 'Valued Guest')

        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; color: white;">
                    <h1>🔔 Reservation Reminder</h1>
                    <p>Your Bella Vista reservation is coming up!</p>
                </div>
                <div style="padding: 30px;">
                    <h2>Hi {guest_name},</h2>
                    <p>This is a friendly reminder about your upcoming reservation at Bella Vista.</p>

                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3>📅 Your Reservation</h3>
                        <p><strong>Date:</strong> {booking_date}</p>
                        <p><strong>Time:</strong> {booking_time}</p>
                        <p><strong>Party Size:</strong> {booking.get('party_size', 1)} guests</p>
                    </div>

                    <p>We look forward to seeing you in {hours_before} hours!</p>

                    <div style="text-align: center; margin-top: 30px;">
                        <p>Questions? Call {self.restaurant_phone}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_reminder_email_text(self, booking: Dict[str, Any], hours_before: int) -> str:
        """Generate reminder email text"""
        return f"""
        BELLA VISTA RESERVATION REMINDER

        Hi {booking.get('guest_name', 'Valued Guest')},

        This is a reminder about your upcoming reservation at Bella Vista.

        Date: {booking.get('date', '')}
        Time: {booking.get('time', '')}
        Party Size: {booking.get('party_size', 1)} guests

        We look forward to seeing you in {hours_before} hours!

        Questions? Call {self.restaurant_phone}
        """

    def _get_reminder_sms_text(self, booking: Dict[str, Any], hours_before: int) -> str:
        """Generate SMS reminder text"""
        return f"""🔔 Reminder: Your Bella Vista reservation for {booking.get('party_size', 1)} is in {hours_before} hours ({booking.get('date')} at {booking.get('time')}). See you soon! 🍽️"""

    def _get_update_email_html(self, booking: Dict[str, Any], change_type: str) -> str:
        """Generate booking update email HTML"""
        guest_name = booking.get('guest_name', 'Valued Guest')

        if change_type == 'cancelled':
            title = "❌ Reservation Cancelled"
            message = "Your reservation has been cancelled as requested."
        elif change_type == 'modified':
            title = "✏️ Reservation Modified"
            message = "Your reservation details have been updated."
        else:
            title = "📝 Reservation Update"
            message = f"Your reservation has been {change_type}."

        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; color: white;">
                    <h1>{title}</h1>
                </div>
                <div style="padding: 30px;">
                    <h2>Hi {guest_name},</h2>
                    <p>{message}</p>

                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3>📅 Reservation Details</h3>
                        <p><strong>Date:</strong> {booking.get('date', '')}</p>
                        <p><strong>Time:</strong> {booking.get('time', '')}</p>
                        <p><strong>Party Size:</strong> {booking.get('party_size', 1)} guests</p>
                        <p><strong>Status:</strong> {booking.get('status', 'Updated')}</p>
                    </div>

                    <div style="text-align: center; margin-top: 30px;">
                        <p>Questions? Call {self.restaurant_phone}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_update_email_text(self, booking: Dict[str, Any], change_type: str) -> str:
        """Generate booking update email text"""
        if change_type == 'cancelled':
            message = "Your reservation has been cancelled as requested."
        elif change_type == 'modified':
            message = "Your reservation details have been updated."
        else:
            message = f"Your reservation has been {change_type}."

        return f"""
        BELLA VISTA RESERVATION UPDATE

        Hi {booking.get('guest_name', 'Valued Guest')},

        {message}

        Current Details:
        Date: {booking.get('date', '')}
        Time: {booking.get('time', '')}
        Party Size: {booking.get('party_size', 1)} guests
        Status: {booking.get('status', 'Updated')}

        Questions? Call {self.restaurant_phone}
        """

    def _get_update_sms_text(self, booking: Dict[str, Any], change_type: str) -> str:
        """Generate SMS update text"""
        if change_type == 'cancelled':
            return f"""❌ Your Bella Vista reservation has been cancelled. Call {self.restaurant_phone} to make a new reservation."""
        elif change_type == 'modified':
            return f"""✏️ Your Bella Vista reservation has been updated to {booking.get('date')} at {booking.get('time')} for {booking.get('party_size', 1)} guests."""
        else:
            return f"""📝 Your Bella Vista reservation has been {change_type}. Call {self.restaurant_phone} for details."""
