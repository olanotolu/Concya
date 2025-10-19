"""
Conversation State Manager for Restaurant Booking
Manages conversation flow and remembers booking information
"""

import re
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger("concya.conversation")

class BookingState(Enum):
    """States of the booking conversation"""
    GREETING = "greeting"
    GATHERING_INFO = "gathering_info"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class ConversationManager:
    """Manages conversation state for restaurant bookings"""

    def __init__(self):
        # In-memory storage for conversations (in production, use Redis/database)
        self.conversations = {}
        self.conversation_timeout = 1800  # 30 minutes

    def _get_conversation_key(self, phone_number: str) -> str:
        """Generate conversation key from phone number"""
        return f"conv_{phone_number}"

    def _cleanup_expired_conversations(self):
        """Remove expired conversations"""
        current_time = datetime.now()
        expired_keys = []

        for key, conv in self.conversations.items():
            if (current_time - conv['last_updated']).seconds > self.conversation_timeout:
                expired_keys.append(key)

        for key in expired_keys:
            del self.conversations[key]

    def get_or_create_conversation(self, phone_number: str) -> Dict[str, Any]:
        """Get existing conversation or create new one"""
        self._cleanup_expired_conversations()

        key = self._get_conversation_key(phone_number)

        if key not in self.conversations:
            self.conversations[key] = {
                'phone_number': phone_number,
                'state': BookingState.GREETING,
                'booking_info': {
                    'party_size': None,
                    'date': None,
                    'time': None,
                    'guest_name': None,
                    'special_requests': None
                },
                'missing_info': [],
                'last_updated': datetime.now(),
                'attempts': 0
            }

        return self.conversations[key]

    def update_conversation(self, phone_number: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update conversation with new information"""
        conv = self.get_or_create_conversation(phone_number)
        conv.update(updates)
        conv['last_updated'] = datetime.now()
        return conv

    def parse_booking_request(self, user_text: str) -> Dict[str, Any]:
        """Parse natural language booking requests to extract information"""
        parsed_info = {
            'party_size': None,
            'date': None,
            'time': None,
            'special_requests': None
        }

        user_lower = user_text.lower()

        # Parse party size - be more specific to avoid confusion with times
        party_patterns = [
            r'(\d+)\s*(?:people|guests?|party|persons?)',
            r'table\s+for\s+(\d+)',
            r'party\s+of\s+(\d+)',
            r'reservation\s+for\s+(\d+)',  # Add this pattern
            r'for\s+(\d+)\s+(?:people|guests?|party|persons?)'  # More specific
        ]

        # Word to number mapping for common numbers
        word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20
        }

        word_patterns = [
            r'(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s*(?:people|guests?|party|persons?)',
            r'table\s+for\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)',
            r'party\s+of\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)',
            r'reservation\s+for\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)',
            r'for\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s*(?:people|guests?|party|persons?)'
        ]

        # First try digit patterns
        for pattern in party_patterns:
            match = re.search(pattern, user_lower)
            if match:
                try:
                    party_size = int(match.group(1))
                    # Only accept reasonable party sizes (1-20)
                    if 1 <= party_size <= 20:
                        parsed_info['party_size'] = party_size
                        break
                except ValueError:
                    continue

        # If no digit match, try word patterns
        if parsed_info['party_size'] is None:
            for pattern in word_patterns:
                match = re.search(pattern, user_lower)
                if match:
                    word = match.group(1).lower()
                    if word in word_to_num:
                        parsed_info['party_size'] = word_to_num[word]
                        break

        # Parse date
        date_patterns = [
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)',
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
            r'tomorrow',
            r'today',
            r'next\s+(\w+)',
            r'(\d{4}-\d{2}-\d{2})'  # YYYY-MM-DD format
        ]

        current_date = datetime.now()

        # Check for relative dates first (these don't need regex matching)
        if 'tomorrow' in user_lower:
            parsed_date = current_date + timedelta(days=1)
            parsed_info['date'] = parsed_date.strftime('%Y-%m-%d')
        elif 'today' in user_lower or 'tonight' in user_lower:
            parsed_info['date'] = current_date.strftime('%Y-%m-%d')

        # Then check for specific date patterns
        for pattern in date_patterns:
            match = re.search(pattern, user_lower)
            if match:
                # Check which pattern matched based on the number of groups
                if len(match.groups()) == 2:
                    # Could be DD Month or Month DD format
                    group1, group2 = match.group(1), match.group(2)
                    if group1 and group1.isdigit() and group2:
                        # DD Month format (e.g., "15 october")
                        day = int(group1)
                        month_name = group2.lower()
                        month_map = {
                            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
                        }
                        if month_name in month_map:
                            year = current_date.year
                            try:
                                parsed_date = datetime(year, month_map[month_name], day)
                                if parsed_date < current_date:
                                    parsed_date = datetime(year + 1, month_map[month_name], day)
                                parsed_info['date'] = parsed_date.strftime('%Y-%m-%d')
                            except ValueError:
                                continue
                    elif group1 and group2 and group2.isdigit():
                        # Month DD format (e.g., "october 15")
                        month_name = group1.lower()
                        day = int(group2)
                        month_map = {
                            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
                        }
                        if month_name in month_map:
                            year = current_date.year
                            try:
                                parsed_date = datetime(year, month_map[month_name], day)
                                if parsed_date < current_date:
                                    parsed_date = datetime(year + 1, month_map[month_name], day)
                                parsed_info['date'] = parsed_date.strftime('%Y-%m-%d')
                            except ValueError:
                                continue
                elif len(match.groups()) == 1:
                    # Could be YYYY-MM-DD or "next X"
                    group1 = match.group(1)
                    if group1 and len(group1) == 10 and '-' in group1:  # YYYY-MM-DD
                        try:
                            parsed_date = datetime.strptime(group1, '%Y-%m-%d')
                            parsed_info['date'] = parsed_date.strftime('%Y-%m-%d')
                        except ValueError:
                            continue
                    # Note: "next X" patterns are handled separately above
                # "tomorrow" and "today" are handled separately above
                break

        # Parse time - be more specific to avoid confusion with party sizes
        time_patterns = [
            r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m|p\.m)',
            r'(\d{1,2})(?::(\d{2}))?\s*o\'?clock',
            r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m|p\.m)',
            r'at\s+(\d{1,2})(?::(\d{2}))?',  # Require "at" for bare numbers
        ]

        for pattern in time_patterns:
            match = re.search(pattern, user_lower)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                am_pm = match.group(3) if len(match.groups()) >= 3 else None

                # Skip if this looks like a party size (single digit without time context)
                if hour < 10 and not am_pm and 'at' not in user_lower and 'o\'clock' not in user_lower:
                    continue

                if am_pm:
                    if am_pm.lower() in ['pm', 'p.m'] and hour != 12:
                        hour += 12
                    elif am_pm.lower() in ['am', 'a.m'] and hour == 12:
                        hour = 0

                try:
                    parsed_time = datetime(2000, 1, 1, hour, minute)
                    parsed_info['time'] = parsed_time.strftime('%H:%M')
                    break
                except ValueError:
                    continue

        # Parse special requests
        special_keywords = [
            'window', 'outside', 'patio', 'indoor', 'quiet', 'romantic',
            'birthday', 'anniversary', 'celebration', 'vegan', 'vegetarian',
            'gluten.free', 'allergic', 'wheelchair', 'accessible'
        ]

        special_parts = []
        for keyword in special_keywords:
            if keyword.replace('.', '') in user_lower:
                special_parts.append(keyword)

        if special_parts:
            parsed_info['special_requests'] = ', '.join(special_parts)

        return parsed_info

    def process_conversation_turn(self, phone_number: str, user_text: str, booking_system=None) -> Tuple[str, BookingState]:
        """Process a conversation turn and return response and new state"""
        start_time = time.time()
        conv = self.get_or_create_conversation(phone_number)

        # Parse the user's message for booking information FIRST
        parse_start = time.time()
        parsed_info = self.parse_booking_request(user_text)
        parse_duration = time.time() - parse_start
        logger.info(f"🔍 Conversation parsing: {parse_duration:.3f}s - Found: {parsed_info}")
        print(f"📝 Parsed info: {parsed_info}")

        # Update booking info with parsed data (only if not None to avoid overwriting with None)
        for key, value in parsed_info.items():
            if value is not None:
                conv['booking_info'][key] = value

        print(f"📋 Updated booking info: {conv['booking_info']}")

        # Try to extract guest name from the message if not already set
        if conv['booking_info']['guest_name'] is None:
            guest_name = self._extract_guest_name(user_text)
            if guest_name:
                conv['booking_info']['guest_name'] = guest_name

        # Determine what information is still missing
        required_fields = ['party_size', 'date', 'time', 'guest_name']
        missing_info = [field for field in required_fields if conv['booking_info'][field] is None]
        print(f"❓ Missing info: {missing_info}")

        # Handle different conversation states
        if conv['state'] == BookingState.GREETING:
            conv['state'] = BookingState.GATHERING_INFO
            return self._get_initial_response(conv), conv['state']

        elif conv['state'] == BookingState.GATHERING_INFO:
            if not missing_info:
                # All info gathered, move to confirmation
                conv['state'] = BookingState.CONFIRMING
                return self._get_confirmation_response(conv), conv['state']
            else:
                # Still missing info, ask for next item
                return self._get_info_request_response(missing_info[0], conv), conv['state']

        elif conv['state'] == BookingState.CONFIRMING:
            # Check if new information was provided that might change the booking
            old_missing = len([field for field in ['party_size', 'date', 'time', 'guest_name'] if conv['booking_info'][field] is None])
            new_missing = len(missing_info)

            # If we gained information (missing count decreased), or user is providing new booking details
            if new_missing < old_missing or parsed_info and any(value is not None for value in parsed_info.values()):
                # New information provided - go back to confirmation with updated details
                if not missing_info:
                    return self._get_confirmation_response(conv), conv['state']
                else:
                    # Still missing info, go back to gathering
                    conv['state'] = BookingState.GATHERING_INFO
                    return self._get_info_request_response(missing_info[0], conv), conv['state']
            elif self._is_confirmation(user_text):
                # User confirmed, complete booking
                if booking_system:
                    # Actually create the booking
                    booking_result = booking_system.create_booking({
                        'party_size': conv['booking_info']['party_size'],
                        'date': conv['booking_info']['date'],
                        'time': conv['booking_info']['time'],
                        'guest_name': conv['booking_info'].get('guest_name', 'Guest'),
                        'phone': phone_number,
                        'special_requests': conv['booking_info'].get('special_requests', '')
                    })

                    if booking_result['success']:
                        conv['state'] = BookingState.COMPLETED
                        return self._get_completion_response(conv), conv['state']
                    else:
                        # Booking failed, stay in confirming state
                        return f"I'm sorry, there was an issue creating your reservation: {booking_result['message']}. Would you like to try again?", conv['state']
                else:
                    # No booking system, just mark as completed
                    conv['state'] = BookingState.COMPLETED
                    return self._get_completion_response(conv), conv['state']
            elif self._is_change_request(user_text):
                # User wants to change something
                return self._handle_changes(user_text, conv), conv['state']
            else:
                # Not a confirmation or change request, ask for clarification
                return "Please say 'yes' or 'confirm' to proceed with the reservation, or let me know what you'd like to change.", conv['state']

        total_duration = time.time() - start_time
        logger.info(f"🧠 Conversation processing: {total_duration:.3f}s")

        return "I'm sorry, I didn't understand that. Could you please clarify?", conv['state']

    def _get_initial_response(self, conv: Dict) -> str:
        """Get initial response after greeting"""
        booking_info = conv['booking_info']

        # Check if we have all required info
        if booking_info['party_size'] and booking_info['date'] and booking_info['time']:
            # User provided complete info in first message
            conv['state'] = BookingState.CONFIRMING
            return self._get_confirmation_response(conv)
        elif booking_info['party_size'] and booking_info['time'] and not booking_info['date']:
            # Have party size and time, missing date - this is common
            return "I have your request for a table for {} at {}. What date would you like to make your reservation for?".format(
                booking_info['party_size'], booking_info['time']
            )
        elif booking_info['party_size'] or booking_info['date'] or booking_info['time']:
            # User provided partial info
            missing = self._get_missing_fields(conv)
            if missing:
                return self._get_info_request_response(missing[0], conv)
        else:
            # No booking info provided
            return "I'd be happy to help you make a reservation at Bella Vista. Could you please let me know how many people will be dining and when you'd like to come?"

    def _get_missing_fields(self, conv: Dict) -> List[str]:
        """Get list of missing required fields"""
        required = ['party_size', 'date', 'time', 'guest_name']
        return [field for field in required if conv['booking_info'][field] is None]

    def _get_info_request_response(self, field: str, conv: Dict) -> str:
        """Get response asking for specific missing information"""
        responses = {
            'party_size': "How many people will be in your party?",
            'date': "What date would you like to make your reservation for?",
            'time': "What time would work best for you?",
            'guest_name': "May I have your name for the reservation?"
        }

        response = responses.get(field, f"Could you please provide the {field.replace('_', ' ')}?")

        # Add context about already gathered info
        context_parts = []
        if conv['booking_info']['party_size']:
            context_parts.append(f"party of {conv['booking_info']['party_size']}")
        if conv['booking_info']['date']:
            context_parts.append(f"on {conv['booking_info']['date']}")
        if conv['booking_info']['time']:
            context_parts.append(f"at {conv['booking_info']['time']}")

        if context_parts and field != 'guest_name':  # Don't add context for name requests
            response = f"For your reservation {' '.join(context_parts)}, {response.lower()}"

        return response

    def _get_confirmation_response(self, conv: Dict) -> str:
        """Get confirmation response with booking summary"""
        info = conv['booking_info']
        summary = f"party of {info['party_size']} on {info['date']} at {info['time']}"

        return f"Thank you for choosing Bella Vista! To confirm your reservation for a {summary}, please say 'yes' or 'confirm'. If you'd like to make any changes, just let me know."

    def _get_completion_response(self, conv: Dict) -> str:
        """Get completion response after successful booking"""
        info = conv['booking_info']
        return f"Perfect! Your reservation for {info['party_size']} guests on {info['date']} at {info['time']} has been confirmed. We'll see you at Bella Vista!"

    def _is_confirmation(self, user_text: str) -> bool:
        """Check if user is confirming the booking"""
        confirm_words = ['yes', 'confirm', 'correct', 'right', 'perfect', 'okay', 'sure', 'book it']
        return any(word in user_text.lower() for word in confirm_words)

    def _extract_guest_name(self, user_text: str) -> Optional[str]:
        """Try to extract a guest name from the user's message"""
        # Look for common name patterns
        name_patterns = [
            r'(?:my name is|i\'?m|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'for\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'under\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:party|reservation)'
        ]

        for pattern in name_patterns:
            match = re.search(pattern, user_text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Basic validation - should be 2-50 chars, contain letters
                if 2 <= len(name) <= 50 and any(c.isalpha() for c in name):
                    return name.title()

        return None

    def _is_change_request(self, user_text: str) -> bool:
        """Check if user is requesting to change booking details"""
        change_words = ['change', 'different', 'modify', 'update', 'wrong', 'instead', 'rather']
        return any(word in user_text.lower() for word in change_words)

    def _handle_changes(self, user_text: str, conv: Dict) -> str:
        """Handle user requests to change booking details"""
        # Reset to gathering mode to allow changes
        conv['state'] = BookingState.GATHERING_INFO
        return "No problem! What would you like to change about your reservation?"
