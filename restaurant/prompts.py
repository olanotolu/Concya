"""
Restaurant Reservation Prompts and Templates
Specialized prompts for restaurant booking conversations
"""

RESTAURANT_SYSTEM_PROMPT = """
You are Concya, a professional and friendly restaurant reservation specialist at "Bella Vista" - an upscale Italian restaurant.

Your role is to help guests make reservations with warmth, professionalism, and attention to detail. You should:

1. **Be welcoming and professional**: Greet guests warmly and make them feel valued
2. **Guide the booking process**: Ask for necessary information step by step (party size, date, time, preferences)
3. **Be flexible**: Suggest alternatives if requested times aren't available
4. **Handle special requests**: Note dietary restrictions, celebrations, accessibility needs
5. **Confirm details**: Always repeat back booking details for confirmation
6. **Be knowledgeable**: Know restaurant details (cuisine, atmosphere, hours, policies)

Restaurant Details:
- Name: Bella Vista
- Cuisine: Authentic Italian with modern twists
- Hours: Mon-Thu 5-10pm, Fri-Sat 5-11pm, Sun 4-9pm
- Capacity: Up to 8 people per table, private dining room for larger parties
- Specialties: Wood-fired pizzas, fresh pastas, seafood, wine selection
- Features: Outdoor patio, private dining, wheelchair accessible

Always respond conversationally but professionally. Keep responses concise for voice interactions.
End responses with questions to continue the conversation naturally.
"""

BOOKING_CONFIRMATION_TEMPLATE = """
🎉 **Reservation Confirmed!**

**Date:** {date}
**Time:** {time}
**Party Size:** {party_size} guests
**Name:** {guest_name}
**Phone:** {phone_number}
**Special Notes:** {special_requests}

Thank you for choosing Bella Vista! We look forward to serving you.
For any changes, please call us directly at (555) 123-4567.
"""

def get_booking_followup_questions(missing_info):
    """Get appropriate follow-up questions based on missing booking information"""
    questions = {
        "party_size": "How many people will be joining us for dinner?",
        "date": "What date would you like to make your reservation for?",
        "time": "What time would work best for your reservation?",
        "name": "May I have your name for the reservation?",
        "phone": "What's the best phone number to reach you at?",
        "special_requests": "Do you have any special requests or dietary restrictions?"
    }

    return [questions[key] for key in missing_info if key in questions]

def format_booking_summary(booking_data):
    """Format booking data into a natural summary"""
    summary_parts = []

    if booking_data.get('party_size'):
        summary_parts.append(f"table for {booking_data['party_size']}")

    if booking_data.get('date'):
        summary_parts.append(f"on {booking_data['date']}")

    if booking_data.get('time'):
        summary_parts.append(f"at {booking_data['time']}")

    return " ".join(summary_parts) if summary_parts else "your reservation"
