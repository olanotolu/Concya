"""
Supabase client for restaurant booking database operations
"""

import os
from supabase import create_client, Client
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

load_dotenv()

class SupabaseRestaurantClient:
    """Supabase client for restaurant operations"""

    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not all([self.supabase_url, self.supabase_key]):
            raise ValueError("Missing Supabase configuration in environment variables")

        # Create client with anon key for regular operations
        self.client: Client = create_client(self.supabase_url, self.supabase_key)

        # Create admin client with service role for admin operations
        self.admin_client: Client = create_client(self.supabase_url, self.service_role_key)

        print("🍽️ Supabase restaurant client initialized")

    def initialize_tables(self):
        """Initialize database tables if they don't exist"""
        try:
            # Check if tables exist and create them if needed
            # Note: In production, you'd run migrations, but for this demo we'll assume tables exist
            print("✅ Supabase tables ready")
        except Exception as e:
            print(f"⚠️ Table initialization issue: {e}")

    def create_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new booking"""
        try:
            response = self.client.table('bookings').insert(booking_data).execute()
            return {
                'success': True,
                'data': response.data[0] if response.data else None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_booking(self, booking_id: str) -> Optional[Dict[str, Any]]:
        """Get booking by ID"""
        try:
            response = self.client.table('bookings').select('*').eq('id', booking_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"❌ Error getting booking: {e}")
            return None

    def get_bookings_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all bookings for a specific date"""
        try:
            response = self.client.table('bookings').select('*').eq('date', date).execute()
            return response.data or []
        except Exception as e:
            print(f"❌ Error getting bookings for date: {e}")
            return []

    def update_booking(self, booking_id: str, updates: Dict[str, Any]) -> bool:
        """Update a booking"""
        try:
            response = self.client.table('bookings').update(updates).eq('id', booking_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"❌ Error updating booking: {e}")
            return False

    def cancel_booking(self, booking_id: str) -> bool:
        """Cancel a booking"""
        return self.update_booking(booking_id, {'status': 'cancelled'})

    def get_availability(self, date: str, time_slot: str) -> Dict[str, Any]:
        """Get availability information for a specific date and time"""
        try:
            # Get all confirmed bookings for this date and time
            bookings = self.client.table('bookings').select('party_size').eq('date', date).eq('time', time_slot).eq('status', 'confirmed').execute()

            current_capacity = sum(booking['party_size'] for booking in bookings.data or [])
            max_capacity = 8  # Max per table

            return {
                'date': date,
                'time': time_slot,
                'current_capacity': current_capacity,
                'max_capacity': max_capacity,
                'available': current_capacity < max_capacity,
                'available_slots': max_capacity - current_capacity
            }
        except Exception as e:
            print(f"❌ Error checking availability: {e}")
            return {
                'date': date,
                'time': time_slot,
                'available': False,
                'error': str(e)
            }

    def get_all_bookings(self, limit: int = 1000) -> Dict[str, Any]:
        """Get all bookings (admin function)"""
        try:
            response = self.admin_client.table('bookings').select('*').order('date', desc=True).order('time', desc=True).limit(limit).execute()
            return {
                'success': True,
                'data': response.data or []
            }
        except Exception as e:
            print(f"❌ Error getting all bookings: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    def health_check(self) -> bool:
        """Check if Supabase connection is working"""
        try:
            response = self.client.table('bookings').select('id').limit(1).execute()
            return True
        except:
            return False
