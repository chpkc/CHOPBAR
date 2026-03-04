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

### Admin Panel

To launch the admin dashboard:

```bash
streamlit run admin_app.py
```
