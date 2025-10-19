"""
Restaurant Booking System
Manages reservations, availability, and booking workflow using Supabase
"""

import json
import os
from datetime import datetime, time
from typing import Dict, List, Optional, Any
from pathlib import Path
from .supabase_client import SupabaseRestaurantClient

class RestaurantBookingSystem:
    """Manages restaurant reservations and availability using Supabase"""

    def __init__(self):
        self.supabase_client = SupabaseRestaurantClient()
        self.supabase_client.initialize_tables()

        # Restaurant operating hours
        self.hours = {
            'monday': {'open': '17:00', 'close': '22:00'},
            'tuesday': {'open': '17:00', 'close': '22:00'},
            'wednesday': {'open': '17:00', 'close': '22:00'},
            'thursday': {'open': '17:00', 'close': '22:00'},
            'friday': {'open': '17:00', 'close': '23:00'},
            'saturday': {'open': '17:00', 'close': '23:00'},
            'sunday': {'open': '16:00', 'close': '21:00'}
        }


    def check_availability(self, date: str, time_slot: str, party_size: int) -> Dict[str, Any]:
        """
        Check if a time slot is available using Supabase

        Args:
            date: Date in YYYY-MM-DD format
            time_slot: Time in HH:MM format
            party_size: Number of guests

        Returns:
            Dict with availability status and suggestions
        """
        # Get availability from Supabase
        availability = self.supabase_client.get_availability(date, time_slot)

        if availability.get('error'):
            return {
                'available': False,
                'message': "I'm having trouble checking availability right now. Please try again."
            }

        available_capacity = availability['available_slots']
        available = party_size <= available_capacity

        if available:
            return {
                'available': True,
                'message': f"Perfect! We have availability for {party_size} guests at {time_slot} on {date}."
            }
        else:
            # Suggest alternatives
            alternatives = self._find_alternatives(date, party_size)
            return {
                'available': False,
                'message': f"I'm sorry, we're fully booked at {time_slot}. {alternatives}"
            }

    def _find_alternatives(self, date: str, party_size: int) -> str:
        """Find alternative time slots"""
        alternatives = []
        common_times = ['18:00', '19:00', '20:00', '21:00']

        for time_slot in common_times:
            if self.check_availability(date, time_slot, party_size)['available']:
                alternatives.append(f"{time_slot}")

        if alternatives:
            return f"Available alternatives: {', '.join(alternatives[:3])}"
        else:
            return "Would you like to try a different date?"

    def create_booking(self, booking_data: Dict) -> Dict[str, Any]:
            """
            Create a new booking using Supabase

            Args:
                booking_data: Dict with booking details

            Returns:
                Dict with booking confirmation or error
            """
            required_fields = ['date', 'time', 'party_size', 'guest_name', 'phone']

            # Check required fields
            missing = [field for field in required_fields if not booking_data.get(field)]
            if missing:
                return {
                    'success': False,
                    'message': f"I need the following information: {', '.join(missing)}"
                }

            # Check availability
            availability = self.check_availability(
                booking_data['date'],
                booking_data['time'],
                booking_data['party_size']
            )

            if not availability['available']:
                return {
                    'success': False,
                    'message': availability['message']
                }

            # Create booking data for Supabase
            booking_id = f"{booking_data['date']}_{booking_data['time']}_{booking_data['guest_name'].replace(' ', '_')}"

            supabase_booking = {
                'id': booking_id,
                'date': booking_data['date'],
                'time': booking_data['time'],
                'party_size': booking_data['party_size'],
                'guest_name': booking_data['guest_name'],
                'phone': booking_data['phone'],
                'special_requests': booking_data.get('special_requests', ''),
                'status': 'confirmed',
                'created_at': datetime.now().isoformat(),
                'notifications_sent': False
            }

            # Save booking to Supabase
            result = self.supabase_client.create_booking(supabase_booking)

            if result['success']:
                # Send confirmation notifications (email + SMS)
                try:
                    from .notifications import RestaurantNotificationService
                    notification_service = RestaurantNotificationService()
                    notification_result = notification_service.send_booking_confirmation(supabase_booking)

                    # Update booking to mark notifications as sent
                    if notification_result['email_sent'] or notification_result['sms_sent']:
                        self.supabase_client.update_booking(booking_id, {'notifications_sent': True})

                    print(f"📧 Notifications sent: Email={notification_result['email_sent']}, SMS={notification_result['sms_sent']}")

                except Exception as e:
                    print(f"⚠️ Notification error: {e}")

                return {
                    'success': True,
                    'booking_id': booking_id,
                    'message': f"Perfect! Your reservation is confirmed for {booking_data['party_size']} guests on {booking_data['date']} at {booking_data['time']}. You'll receive confirmation details via email and SMS.",
                    'notifications_sent': True
                }
            else:
                return {
                    'success': False,
                    'message': "I'm having trouble saving your reservation right now. Please try again."
                }

    def get_booking(self, booking_id: str) -> Optional[Dict]:
        """Get booking details by ID using Supabase"""
        return self.supabase_client.get_booking(booking_id)

    def cancel_booking(self, booking_id: str) -> bool:
        """Cancel a booking using Supabase"""
        return self.supabase_client.cancel_booking(booking_id)

    def validate_date_time(self, date: str, time_slot: str) -> Dict[str, Any]:
        """Validate if date and time are within operating hours"""
        try:
            # Parse date
            booking_date = datetime.strptime(date, '%Y-%m-%d')
            day_name = booking_date.strftime('%A').lower()

            if day_name not in self.hours:
                return {'valid': False, 'message': "Sorry, we're closed on that day."}

            # Parse time
            booking_time = datetime.strptime(time_slot, '%H:%M').time()
            open_time = datetime.strptime(self.hours[day_name]['open'], '%H:%M').time()
            close_time = datetime.strptime(self.hours[day_name]['close'], '%H:%M').time()

            if booking_time < open_time or booking_time > close_time:
                return {
                    'valid': False,
                    'message': f"Our hours on {day_name.title()} are {self.hours[day_name]['open']} to {self.hours[day_name]['close']}."
                }

            return {'valid': True, 'message': "Time is within operating hours."}

        except ValueError:
            return {'valid': False, 'message': "Please provide date in YYYY-MM-DD format and time in HH:MM format."}
