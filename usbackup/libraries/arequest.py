import asyncio
import requests

async def arequest_post(*args, **kwargs) -> requests.Response:
    return await asyncio.to_thread(requests.post, *args, **kwargs)
    
async def arequest_get(*args, **kwargs) -> requests.Response:
    return await asyncio.to_thread(requests.get, *args, **kwargs)