import asyncio

async def afwrite(file_path: str, data: str, *, mode: str = 'w') -> None:
    def write(file_path: str, data: str, *, mode: str = 'w') -> None:
        with open(file_path, mode) as f:
            f.write(data)

    await asyncio.to_thread(write, file_path, data, mode=mode)

async def afread(file_path: str) -> str:
    def read(file_path: str) -> str:
        with open(file_path, 'r') as f:
            return f.read()
        
    return await asyncio.to_thread(read, file_path)