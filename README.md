# CHOPBAR - Barbershop Booking Assistant

This project implements a dynamic system prompt generator for a barbershop booking assistant AI.

## Structure

- `data/barbershop.json`: Contains the dynamic data for barbers, services, and working hours.
- `prompts/system_prompt.txt`: The template for the AI system prompt.
- `main.py`: A script that loads the data and prompt template, then generates the final system prompt ready for LLM injection.

## Usage

Run the script to see the generated prompt:

```bash
python3 main.py
```

## Next Steps

To make this a fully functional bot, you can:
1.  Integrate with an LLM API (OpenAI, Anthropic, etc.).
2.  Build a frontend (Web, Telegram, CLI).
3.  Implement the booking confirmation logic (parsing the `<<<BOOKING: ...>>>` output).
