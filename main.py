import json
import os

def load_data():
    with open('data/barbershop.json', 'r') as f:
        return json.load(f)

def load_prompt():
    with open('prompts/system_prompt.txt', 'r') as f:
        return f.read()

def format_prompt(prompt_template, data):
    # Format barbers list
    barbers_str = "\n".join([f"- {b['name']} ({b['specialty']}, {b['experience']})" for b in data['barbers']])
    
    # Format services list
    services_str = "\n".join([f"- {s['name']}: ${s['price']} ({s['duration_minutes']} min)" for s in data['services']])
    
    # Format hours
    hours_list = []
    for day, hours in data['hours'].items():
        day_formatted = day.replace('_', '-').title()
        hours_list.append(f"- {day_formatted}: {hours}")
    hours_str = "\n".join(hours_list)
    
    # Replace placeholders
    prompt = prompt_template.replace('{barbers}', barbers_str)
    prompt = prompt.replace('{services}', services_str)
    prompt = prompt.replace('{hours}', hours_str)
    
    return prompt

def main():
    data = load_data()
    raw_prompt = load_prompt()
    system_prompt = format_prompt(raw_prompt, data)
    
    print("--- Generated System Prompt ---")
    print(system_prompt)
    print("\n--- Ready for LLM Integration ---")
    # Here you would typically send this system_prompt to an LLM API (e.g., OpenAI, Anthropic)
    # along with user messages.

if __name__ == "__main__":
    main()
