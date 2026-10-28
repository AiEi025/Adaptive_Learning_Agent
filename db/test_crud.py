import asyncio
import selectors

from db.crud import Crud


async def run_test():
    crud = Crud('Amirali')
    await crud.open()

    try:
        # await crud.register(
        #     "test_user_0",
        #     "ExamplePassword123!",
        # )
        # assert await crud.is_exist('test_user_001')
        # assert not await crud.is_exist('test_u')
        result = await crud.update_profile(
        update_col='last_login'#, param_change='fewfadffewfwe'
    )
        assert result is None
    finally:
        await crud.close()


def test_insert():
    asyncio.run(
        run_test(),
        loop_factory=lambda: asyncio.SelectorEventLoop(
            selectors.SelectSelector()
        ),
    )