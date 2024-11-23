import asyncio
import json
import websockets
import os

from colorama import Fore

from camel.agents import ChatAgent
from camel.configs import ChatGPTConfig
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from camel.societies.workforce import Workforce
from camel.tasks import Task

from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType
from camel.configs import ChatGPTConfig
from camel.messages import BaseMessage
from camel.agents import ChatAgent

gpt_model = ModelFactory.create(
    model_platform=ModelPlatformType.OPENAI,
    model_type=ModelType.GPT_4O_MINI,
    api_key="your-api-key",
    # url="https://api.mixrai.com/v1",
    model_config_dict=ChatGPTConfig().as_dict(),
)

ollama_model = ModelFactory.create(
    model_platform=ModelPlatformType.OLLAMA,
    model_type="llama3.2",
    url="http://localhost:11434/v1", # Optional
    model_config_dict={
        "temperature": 1.0,
        "max_tokens": 4096,
    },
)

g_model = gpt_model

MSGBLOCK = """
User: {username}
Comment: {comment}
"""

WORKER_SYSMSG = """
You are an interviewee participating in a group interview.

Your task is to respond to questions and discussions based on the topic being discussed, providing thoughtful and relevant answers.

You can accept input from other interviewees and adjust your responses accordingly, taking into account the context of the ongoing discussion.

You can agree or disagree other's opinion, but also you should give a deep insight reason.

You should be aggressive, and give deep insight about the topic, because you really want to win in this interview.

Your username is {username}.

You are talking about the topic {topic}.
"""

WORKER_PROMPT = """
Task: Now you should post your comment, according to the discussion context. Remember, you are {username}.
Answer(just put your comment, never put username):
"""

CONTROLLER_SYSMSG = """
You are an asistent in a group interview discussion. Your task is to moderate the discussion by selecting one of the interviewees to post comments based on the discussion context.

You will receive the current discussion content context, and your responsibility is choose an appropriate interviewee from the **interviewee list** to respond.

**interviewee list**: {usernames}
"""

CONTROLLER_PROMPT = """
Question: According to the discussion context, next interviewee should be which one in the **interviewee list**?
Answer(just select your choice from the appropriate interviewee list, never given additional text):
"""


class WorkerAgent(ChatAgent):

    def __init__(self, username, topic):
        self.username = username
        ChatAgent.__init__(
            self,
            system_message=WORKER_SYSMSG.format(username=username, topic=topic),
            model=g_model,
            # output_language="chinese",
        )


class ControllerAgent:

    def __init__(self, topic, users):
        self.worker_agents = {}
        for user in users:
            self.worker_agents[user] = WorkerAgent(user, topic)

        self.controller_agent = ChatAgent(
            system_message=CONTROLLER_SYSMSG.format(usernames=",".join(users)),
            model=g_model,
        )

    def step(self, context):
        self.controller_agent.reset()
        reply = self.controller_agent.step(context + CONTROLLER_PROMPT)
        nextone = reply.msgs[0].content.lower()
        agent = self.worker_agents[nextone]
        agent.reset()
        comment = agent.step(context + WORKER_PROMPT.format(username=agent.username)).msgs[0].content
        return (agent.username, comment)


class Server:

    def __init__(self):
        self.clients = set()
        context = MSGBLOCK.format(
            username="interviewer",
            comment="Now who want to talk about the topic first?"
        )

    def add_client(self, client):
        self.clients.add(client)

    def append_context(self, username, comment):
        self.context += MSGBLOCK.format(username=username, comment=comment)

    async def broadcast(self, msg):
        for client in self.clients:
            await client.send(msg)


clients = set()

topic = "Make a promotion plan for our new shampoo product on tiktok."
context = ""

async def handle_client(websocket):
    global clients
    global context
    print(f"New client connected: {websocket.remote_address}")
    clients.add(websocket)
    async for message in websocket:
        j = json.loads(message)
        context += MSGBLOCK.format(username=j["username"], comment=j["comment"])
        for client in clients:
            await client.send(message)


async def start_websocket_server():
    server = await websockets.serve(handle_client, "localhost", 8765, ping_interval=None)
    print("Server started on ws://localhost:8765")
    await server.wait_closed()


async def start_controller():
    global clients
    global context
    controller = ControllerAgent(topic, ["coco", "jack", "andy", "tommy", "chloe"])
    context = MSGBLOCK.format(username="interviewer", comment="Now who want to talk about the topic first?")
    while True:
        # poll context each 10 secs
        await asyncio.sleep(10)
        (username, comment) = controller.step(context)
        for client in clients:
            data = { "username": username, "comment": comment }
            await client.send(json.dumps(data))
        context += MSGBLOCK.format(username=username, comment=comment)
        print(Fore.GREEN + username)
        print(Fore.RESET + comment)


async def main():
    t1 = asyncio.create_task(start_websocket_server())
    t2 = asyncio.create_task(start_controller())
    await t1
    await t2

if __name__ == "__main__":
    asyncio.run(main())

