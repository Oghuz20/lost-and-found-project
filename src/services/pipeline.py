import asyncio
from typing import List, Any, Dict
from src.models import Item, ItemStatus
from src.services.concurrency.batch_runner import BatchRunner
from src.services.concurrency.rate_limiter import TokenBucketRateLimiter


class PipelineService:
    """
    Оркестратор обработки данных: связывает VLM, эмбеддинг, 
    rate limiter и параллельную регистрацию.
    """

    def __init__(self, ai_service: Any, repository: Any, max_concurrency: int = 5) -> None:
        self.ai_service = ai_service
        self.repository = repository
        self.batch_runner = BatchRunner(max_concurrency=max_concurrency)
        self.rate_limiter = TokenBucketRateLimiter()

    async def register_item(
        self,
        status: str,
        user_text: str,
        image_path: str,
    ) -> Item:
        """
        Одиночная регистрация с учетом лимитов токенов/запросов.
        """
        await self.rate_limiter.acquire(estimated_tokens=500)
        
        # Получаем текстовое описание предмета через VLM
        vlm_desc = await self.ai_service.describe_item_async(image_path, user_text)
        
        # Получаем векторный эмбеддинг для поиска
        search_text = vlm_desc if isinstance(vlm_desc, str) else str(vlm_desc)
        vector = await self.ai_service.embed_async(search_text)

        # Приводим vlm_desc к формату dict для Pydantic-модели
        if not isinstance(vlm_desc, dict):
            if hasattr(vlm_desc, "model_dump"):
                vlm_dict = vlm_desc.model_dump()
            elif hasattr(vlm_desc, "__dict__"):
                vlm_dict = vlm_desc.__dict__
            else:
                vlm_dict = {"description": str(vlm_desc)}
        else:
            vlm_dict = vlm_desc

        # Создаем Pydantic-модель Item для передачи в Person A repository
        item_model = Item(
            status=ItemStatus(status),
            user_text=user_text,
            image_path=image_path,
            vlm_description=vlm_dict,
            embedding=vector,
        )

        # Сохраняем в базу данных через слой Person A
        saved_item = await self.repository.save_item(item_model)
        return saved_item

    async def register_batch(self, items_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Параллельная регистрация списка предметов.
        """
        async def _process_one(data: Dict[str, Any]) -> Dict[str, Any]:
            saved_item = await self.register_item(
                status=data["status"],
                user_text=data.get("user_text", ""),
                image_path=data["image_path"],
            )
            # Возвращаем словарь или Pydantic-модель
            return saved_item.model_dump() if hasattr(saved_item, "model_dump") else saved_item

        raw_results = await self.batch_runner.run_batch(items_data, _process_one)

        results: List[Dict[str, Any]] = []
        for data, res in zip(items_data, raw_results):
            if isinstance(res, BaseException):
                results.append({
                    "status": data.get("status"),
                    "image_path": data.get("image_path"),
                    "error": str(res),
                    "error_type": res.__class__.__name__,
                })
            else:
                results.append(res)
        return results