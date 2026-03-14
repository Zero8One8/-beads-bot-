"""
Квизы: Узнай свой камень и Тотемный камень.
"""
import logging
import json
from collections import defaultdict
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database.models import QuizModel, TotemModel
from src.keyboards.quiz import get_quiz_keyboard, get_totem_keyboard, get_quiz_result_keyboard
from src.services.analytics import FunnelTracker

logger = logging.getLogger(__name__)
router = Router()


class QuizStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()


class TotemStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()


@router.callback_query(F.data == "quiz")
async def quiz_start(callback: CallbackQuery, state: FSMContext):
    """Начало квиза 'Узнай свой камень'."""
    await FunnelTracker.track(callback.from_user.id, 'quiz_start')
    
    questions = QuizModel.get_questions()
    if not questions:
        await callback.message.edit_text(
            "🔮 *УЗНАЙ СВОЙ КАМЕНЬ*\n\n"
            "Квиз временно недоступен.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    await state.update_data(questions=questions, step=0, answers=[])
    await state.set_state(QuizStates.q1)
    
    q = questions[0]
    await callback.message.edit_text(
        f"🔮 *ВОПРОС 1 ИЗ {len(questions)}*\n\n{q['question']}",
        reply_markup=get_quiz_keyboard(json.loads(q['options']))
    )
    await callback.answer()


@router.callback_query(QuizStates.q1, F.data.startswith("quiz_ans_"))
@router.callback_query(QuizStates.q2, F.data.startswith("quiz_ans_"))
@router.callback_query(QuizStates.q3, F.data.startswith("quiz_ans_"))
@router.callback_query(QuizStates.q4, F.data.startswith("quiz_ans_"))
@router.callback_query(QuizStates.q5, F.data.startswith("quiz_ans_"))
async def quiz_answer(callback: CallbackQuery, state: FSMContext):
    """Обработка ответа."""
    data = await state.get_data()
    step = data.get('step', 0)
    answers = data.get('answers', [])
    questions = data.get('questions', [])
    
    answer_index = int(callback.data.split('_')[-1])
    answers.append(answer_index)
    await state.update_data(answers=answers)
    
    next_step = step + 1
    if next_step >= len(questions):
        # Квиз завершён
        recommended = calculate_stone(answers)
        QuizModel.save_result(callback.from_user.id, answers, recommended)
        await FunnelTracker.track(callback.from_user.id, 'quiz_complete', recommended)
        
        await state.clear()
        await callback.message.edit_text(
            f"🎉 *ВАШ КАМЕНЬ: {recommended}*\n\n"
            f"Этот камень идеально подходит вам по результатам теста.\n"
            f"Посмотрите браслеты с ним в нашем каталоге!",
            reply_markup=get_quiz_result_keyboard(recommended)
        )
        await callback.answer()
        return
    
    await state.update_data(step=next_step)
    next_state = getattr(QuizStates, f'q{next_step+1}')
    await state.set_state(next_state)
    
    q = questions[next_step]
    await callback.message.edit_text(
        f"🔮 *ВОПРОС {next_step+1} ИЗ {len(questions)}*\n\n{q['question']}",
        reply_markup=get_quiz_keyboard(json.loads(q['options']))
    )
    await callback.answer()


def calculate_stone(answers: list) -> str:
    """Простой расчёт камня по ответам (можно усложнить)."""
    mapping = {
        0: 'Аметист',
        1: 'Розовый кварц',
        2: 'Цитрин',
        3: 'Тигровый глаз',
        4: 'Лабрадорит'
    }
    if answers and answers[-1] in mapping:
        return mapping[answers[-1]]
    return 'Горный хрусталь'


@router.callback_query(F.data == "totem")
async def totem_start(callback: CallbackQuery, state: FSMContext):
    """Начало тотемного квиза."""
    questions = TotemModel.get_questions()
    if not questions:
        await callback.message.edit_text(
            "🦊 *ТОТЕМНЫЙ КАМЕНЬ*\n\n"
            "Квиз временно недоступен.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    await state.update_data(questions=questions, step=0, answers={})
    await state.set_state(TotemStates.q1)
    
    q = questions[0]
    await callback.message.edit_text(
        f"🦊 *ТОТЕМНЫЙ КВИЗ*\n\n{q['question']}",
        reply_markup=get_totem_keyboard(json.loads(q['options']))
    )
    await callback.answer()


@router.callback_query(TotemStates.q1, F.data.startswith("totem_ans_"))
@router.callback_query(TotemStates.q2, F.data.startswith("totem_ans_"))
@router.callback_query(TotemStates.q3, F.data.startswith("totem_ans_"))
@router.callback_query(TotemStates.q4, F.data.startswith("totem_ans_"))
@router.callback_query(TotemStates.q5, F.data.startswith("totem_ans_"))
async def totem_answer(callback: CallbackQuery, state: FSMContext):
    """Обработка ответа на тотемный квиз."""
    data = await state.get_data()
    step = data.get('step', 0)
    answers = data.get('answers', {})
    questions = data.get('questions', [])
    
    q_id = questions[step]['id']
    answer_idx = int(callback.data.split('_')[-1])
    answers[str(q_id)] = answer_idx
    await state.update_data(answers=answers)
    
    next_step = step + 1
    if next_step >= len(questions):
        # Квиз завершён
        top3 = calculate_totem(answers, questions)
        TotemModel.save_result(callback.from_user.id, answers, top3)
        await FunnelTracker.track(callback.from_user.id, 'totem_complete', ','.join(top3))
        
        await state.clear()
        text = "✨ *ВАШИ ТОТЕМНЫЕ КАМНИ:*\n\n"
        for i, stone in enumerate(top3, 1):
            text += f"{i}. {stone}\n"
        text += "\nЭти камни отражают вашу глубинную сущность."
        
        await callback.message.edit_text(
            text,
            reply_markup=get_quiz_result_keyboard(top3[0])
        )
        await callback.answer()
        return
    
    await state.update_data(step=next_step)
    next_state = getattr(TotemStates, f'q{next_step+1}')
    await state.set_state(next_state)
    
    q = questions[next_step]
    await callback.message.edit_text(
        f"🦊 *ВОПРОС {next_step+1} ИЗ {len(questions)}*\n\n{q['question']}",
        reply_markup=get_totem_keyboard(json.loads(q['options']))
    )
    await callback.answer()


def calculate_totem(answers: dict, questions: list) -> list:
    """Расчёт топ-3 камней для тотемного квиза."""
    scores = defaultdict(int)
    
    for q in questions:
        q_id = str(q['id'])
        if q_id in answers:
            weights = json.loads(q['weights']) if q['weights'] else {}
            answer_val = answers[q_id]
            # В weights ключи — названия камней, значения — баллы
            for stone, points in weights.items():
                scores[stone] += points
    
    sorted_stones = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3 = [stone for stone, _ in sorted_stones[:3]]
    
    while len(top3) < 3:
        top3.append("Горный хрусталь")
    
    return top3