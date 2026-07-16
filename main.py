import asyncio
from autopayroll.interface import Interface

def main():
    interface = Interface()
    # Correctly await the async main loop
    asyncio.run(interface.main())

if __name__ == "__main__":
    main()
