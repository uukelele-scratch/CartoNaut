import google.generativeai as genai
import re
import socketio
import time
import requests
from PIL import Image
from io import BytesIO
import traceback
from elevenlabs.client import ElevenLabs
from elevenlabs import stream
from pyht import Client as PlayHT
from pyht.client import TTSOptions

config = {
    "GEMINI_API_KEY": "", # Replace with your Google Gemini API Key
    "ELEVENLABS_API_KEY": "", # Replace with your ElevenLabs API Key
    "PLAYHT_API_KEY": "", # Replace with your PlayHT API Key
    "PLAYHT_USER_ID": "", # Replace with your PlayHT User ID
    "AUDIO": "", # Either "ElevenLabs", "PlayHT", or "" (no audio)
    "VOICE": "", # Leave this empty if you want to use the default voice
    "GOAL": "Locate the target. Then, pathfind towards the target.",
    "TARGET": "A red ball",
    "SUCCESS_CRITERIA": "The goal is complete when you have arrived at the target."
}

print("Setting up AI...")

genai.configure(api_key=config.get("GEMINI_API_KEY", "0"))

goal = config.get("GOAL", "Locate the target. Then, pathfind towards the target.")
target = config.get("TARGET")
success_criteria = config.get("SUCCESS_CRITERIA", "The goal is complete when you have arrived at the target.")
audio = config.get("AUDIO")
if audio == "ElevenLabs":
    elevenlabs = ElevenLabs(
        api_key=config.get("ELEVENLABS_API_KEY", "0"),
    )
elif audio == "PlayHT":
    playht = PlayHT(
        api_key=config.get("PLAYHT_API_KEY"),
        user_id=config.get("PLAYHT_USER_ID")
    )

    playhtoptions = TTSOptions(voice=config.get("VOICE", "s3://voice-cloning-zero-shot/775ae416-49bb-4fb6-bd45-740f205d20a1/jennifersaad/manifest.json"))
else:
    pass

def say(text):
    if not audio:
        return
    if audio == "ElevenLabs":
        audio_stream = elevenlabs.text_to_speech.convert_as_stream(
            text=text,
            voice_id=config.get("VOICE", "JBFqnCBsd6RMkjVDRZzb"),
            model_id="eleven_multilingual_v2"
        )
        stream(audio_stream)
    elif audio == "PlayHT":
        audio_stream = playht.tts(text, playhtoptions)
        stream(audio_stream)
    else:
        return


model = genai.GenerativeModel("gemini-2.5-flash-lite")



print("Connecting to server...")
sio = socketio.Client()
sio.connect('http://zero.local:5000')
print("Server connected.")

def send_signal(direction, strength=100):
        if sio.connected:
            message = f"{direction}:{strength}"
            try:
                sio.emit('message', message)
                print(f"Sent: {message}")
            except Exception as e:
                print(f"Error sending message: {e}")
        else:
            print("Socket.IO client is not connected.")

init = """
You are an AI controlling a robot. You will receive images from the robot's camera (if you see wires, ignore them, they are part of the robot) and you must send commands to the robot to move it around.
Commands are formatted as '!name(\"arg1\", \"arg2\")' as you would in perhaps python, but with '!' prefixed.
No args mean still use empty () after !name. Note: ALL arguments must be strings. Dictionary, List, Int, Float etc. conversion will be handled by the command parser if necessary.
Here are the commands you can use:
!forward(duration, speed) - Move the robot forward for the specified duration (in seconds) at the specified speed (0-100).
!backward(duration, speed) - Move the robot backward for the specified duration (in seconds) at the specified speed (0-100).
!left(duration, speed) - Turn the robot left for the specified duration (in seconds) at the specified speed (0-100).
!right(duration, speed) - Turn the robot right for the specified duration (in seconds) at the specified speed (0-100).
The speed must be an integer, but the duration can be either an integer or a float.

In your response, provide the commands you are using, as well as a well-reasoned, chain-of-thought as to why you are arriving at that decision.
Reason first, then command. Enclose reasoning within <think>REASONING</think> tags.

Tips:
    - If you see a wall in front of you, turn around! Don't be afraid to turn at high speeeds, as well.
    - Sometimes, you may need to turn around to get a better view of the room.
    - The goal is in the current room, so you don't need to leave the room to find it.
    - Note that the forward and backward functions might be a little wonky, and move slightly to the left or right. You can solve this by using !right or !left with a low duration and low speed.
    - Do not be afraid to use long distances and high speeds to get to your goal faster. You should use at least 80 speed for forward/backward commands if the target is a long distance away, but choose a lower speed when turning. When turning, prioritize duration over speed. However, never go below 35 for speed.
    - IMPORTANT: Build a 3D map of the room in your memory as you get images. This will help you navigate better, and understand the layout of the room.
    - Do not include commands in your reasoning, as they will get executed as well.
    - Adapt. If you have, for example, turned multiple times with a speed of 50 and see no progress, increase the speed to 60 or 70. If you are still not seeing progress, increase the speed further. If you are moving too fast, decrease the speed.
    
You MUST include one command in each response, UNTIL you have reached the goal.
When you have reached the goal, do not use any further commands.

Here is your current goal:
$GOAL

Here is the target:
$TARGET

Here is the success criteria:
$SUCCESS

Here is an example of a response you may make:
SYSTEM: [image]
<think>Okay, I see the target in front of me. The target is a bit to the left, so I'll move left a little, then move forwards to get to the target.</think>
!left(1, 35)
SYSTEM:[image] Your command(s) have finished executing successfully. Here are the results: Command 'left' returned with: Success
<think>I have moved left, and now I will move forwards to get to the target. A speed of 80 should do, and I think it will take around 3 seconds.</think>
!forward(3, 80)
SYSTEM:[image] Your command(s) have finished executing successfully. Here are the results: Command 'forward' returned with: Success
<think>I have moved forwards, and I have reached the target. The goal is complete.</think>
"""

def latest_image():
    response = requests.get('http://zero.local:5000/')
    image = Image.open(BytesIO(response.content))
    image.show()
    return image

messages = []
goal_message = init.replace("$GOAL", goal).replace("$SUCCESS", success_criteria).replace("$TARGET", target)
messages.append({"role":"user", "parts":[goal_message]})

def process_output(output):
    def w(duration, speed):
        send_signal("w", speed)
        time.sleep(float(duration))
        send_signal("stop")
        return "Success"

    def s(duration, speed):
        send_signal("s", speed)
        time.sleep(float(duration))
        send_signal("stop")
        return "Success"

    def a(duration, speed):
        send_signal("a", speed)
        time.sleep(float(duration))
        send_signal("stop")
        return "Success"
    
    def d(duration, speed):
        send_signal("d", speed)
        time.sleep(float(duration))
        send_signal("stop")
        return "Success"

    function_map = {
        "forward": w,
        "backward": s,
        "left": a,
        "right": d
    }
    
    pattern = r'!([a-zA-Z_]+)\(([^)]*)\)'
    matches = re.findall(pattern, output)

    output = ""
    for command, args_str in matches:
        command_name = command
        args = re.findall(r'"(.*?)"', args_str)
        if command_name in function_map:
            try:
                output += f"\n\nCommand '{command_name}' returned with: {function_map[command_name](*args)}"
            except Exception as e:
                output += f"\n\nCommand '{command_name}' returned with an Exception:\n{traceback.format_exc()}"
        else:
            output += f"\n\nCommand '{command_name}' not found."
    
    return output if output != "" else None

print("Starting...")
print(f"Current Goal: {goal}")
print(f"Target: {target}")
print(f"Success Criteria: {success_criteria}")
try:
    while True:
        print("Fetching image...")
        messages.append({"role":"user","parts":[latest_image()]})
        print("Image fetched! Generating response...")
        response = model.generate_content(messages).text
        messages.append({"role":"model","parts":[response]})
        print(response)
        reasoning = response.split("<think>")[1].split("</think>")[0]
        say(reasoning)
        p = process_output(response)
        print(p)
        if not p:
            print(f"Agent did not use a command.")
            break
        else:
            messages.append({"role":"user","parts":[f"Your command(s) have finished executing successfully. Here are the results:\n\n\n{p}"]})
finally:
    send_signal("stop")
    sio.disconnect()
