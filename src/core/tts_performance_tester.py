#!/usr/bin/env python3
"""
TTSPerformanceTester: Инструмент для сравнения производительности TTS движков
Сравнивает качество, скорость и надежность разных TTS движков для русского и украинского языков
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

from pydub import AudioSegment
import subprocess

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import config
from core.tts_engine_factory import TTSEngineFactory, TTSEngine


@dataclass
class PerformanceResult:
    """Результат тестирования производительности TTS"""
    engine: TTSEngine
    language: str
    text: str
    success: bool
    duration_seconds: float
    audio_file_path: Optional[str]
    audio_duration_seconds: Optional[float]
    file_size_bytes: Optional[int]
    quality_score: Optional[float]  # 1-10, субъективная оценка
    error_message: Optional[str]


@dataclass 
class ComparisonReport:
    """Отчет сравнения движков"""
    language: str
    test_texts: List[str]
    results: List[PerformanceResult]
    summary: Dict
    timestamp: str


class TTSPerformanceTester:
    """Тестер производительности TTS движков"""
    
    def __init__(self):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.tts_factory = TTSEngineFactory()
        
        # Тестовые тексты для разных языков
        self.test_texts = {
            'ru': [
                "Привет, это короткий тест русского TTS.",
                "Сегодня отличная погода для прогулки по парку. Солнце светит ярко, и птицы поют свои мелодичные песни.",
                "Искусственный интеллект становится всё более важной частью нашей повседневной жизни, помогая решать сложные задачи.",
                "В технологической сфере происходят быстрые изменения, которые влияют на способы работы и общения людей по всему миру."
            ],
            'uk': [
                "Привіт, це короткий тест українського TTS.",
                "Сьогодні чудова погода для прогулянки парком. Сонце світить яскраво, і пташки співають свої мелодійні пісні.",
                "Штучний інтелект стає все більш важливою частиною нашого повсякденного життя, допомагаючи вирішувати складні завдання.",
                "У технологічній сфері відбуваються швидкі зміни, які впливають на способи роботи та спілкування людей по всьому світу."
            ]
        }
        
        self.logger.info("🧪 TTSPerformanceTester инициализирован")
    
    def test_engine_performance(
        self, 
        engine: TTSEngine, 
        language: str, 
        test_text: str
    ) -> PerformanceResult:
        """Тестирование производительности одного движка"""
        
        self.logger.info(f"🔬 Тестируем {engine.value} для {language}: '{test_text[:30]}...'")
        
        start_time = time.time()
        
        try:
            # Синтез речи
            audio_file = self.tts_factory.synthesize_with_engine(test_text, language, engine)
            
            duration = time.time() - start_time
            
            if audio_file and Path(audio_file).exists():
                # Анализ результата
                file_size = Path(audio_file).stat().st_size
                audio_duration = self._get_audio_duration(audio_file)
                quality_score = self._estimate_quality_score(audio_file, test_text, language)
                
                result = PerformanceResult(
                    engine=engine,
                    language=language,
                    text=test_text,
                    success=True,
                    duration_seconds=duration,
                    audio_file_path=audio_file,
                    audio_duration_seconds=audio_duration,
                    file_size_bytes=file_size,
                    quality_score=quality_score,
                    error_message=None
                )
                
                self.logger.info(f"✅ {engine.value}: {duration:.2f}s, аудио: {audio_duration:.2f}s, качество: {quality_score:.1f}/10")
                
            else:
                result = PerformanceResult(
                    engine=engine,
                    language=language,
                    text=test_text,
                    success=False,
                    duration_seconds=duration,
                    audio_file_path=None,
                    audio_duration_seconds=None,
                    file_size_bytes=None,
                    quality_score=None,
                    error_message="Файл не создан"
                )
                
                self.logger.warning(f"❌ {engine.value}: синтез не удался за {duration:.2f}s")
        
        except Exception as e:
            duration = time.time() - start_time
            result = PerformanceResult(
                engine=engine,
                language=language,
                text=test_text,
                success=False,
                duration_seconds=duration,
                audio_file_path=None,
                audio_duration_seconds=None,
                file_size_bytes=None,
                quality_score=None,
                error_message=str(e)
            )
            
            self.logger.error(f"💥 {engine.value}: ошибка {e} за {duration:.2f}s")
        
        return result
    
    def compare_engines_for_language(self, language: str) -> ComparisonReport:
        """Сравнение всех доступных движков для языка"""
        
        self.logger.info(f"🏁 Начинаем сравнение TTS движков для языка: {language}")
        
        available_engines = self.tts_factory.get_available_engines()
        test_engines = [e for e in available_engines if e != TTSEngine.AUTO]
        
        test_texts = self.test_texts.get(language, [f"Тест TTS для языка {language}"])
        
        results = []
        
        for engine in test_engines:
            for text in test_texts:
                result = self.test_engine_performance(engine, language, text)
                results.append(result)
                
                # Небольшая пауза между тестами
                time.sleep(0.5)
        
        # Создаем сводку
        summary = self._create_summary(results, language)
        
        report = ComparisonReport(
            language=language,
            test_texts=test_texts,
            results=results,
            summary=summary,
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        self._log_comparison_results(report)
        
        return report
    
    def compare_russian_vs_ukrainian(self) -> Dict[str, ComparisonReport]:
        """Сравнение TTS для русского и украинского языков"""
        
        self.logger.info("🇷🇺🇺🇦 Сравнение русского и украинского TTS")
        
        reports = {}
        
        # Тестируем русский
        reports['ru'] = self.compare_engines_for_language('ru')
        
        # Тестируем украинский  
        reports['uk'] = self.compare_engines_for_language('uk')
        
        # Создаем сравнительный анализ
        self._log_language_comparison(reports)
        
        return reports
    
    def _get_audio_duration(self, audio_file: str) -> Optional[float]:
        """Получить длительность аудио файла"""
        try:
            audio = AudioSegment.from_file(audio_file)
            return len(audio) / 1000.0  # в секундах
        except Exception as e:
            self.logger.debug(f"Не удалось получить длительность {audio_file}: {e}")
            return None
    
    def _estimate_quality_score(self, audio_file: str, text: str, language: str) -> float:
        """Оценка качества аудио (простая эвристика)"""
        try:
            # Базовая оценка на основе размера файла и длительности
            file_size = Path(audio_file).stat().st_size
            duration = self._get_audio_duration(audio_file)
            
            if not duration or duration == 0:
                return 1.0
            
            # Битрейт как индикатор качества
            bitrate = (file_size * 8) / duration / 1000  # kbps
            
            # Эвристическая оценка качества
            if bitrate > 128:
                quality = 8.5
            elif bitrate > 64:
                quality = 7.0
            elif bitrate > 32:
                quality = 5.5
            else:
                quality = 3.0
            
            # Корректировка для известных проблем
            audio_path_str = str(audio_file).lower()
            if 'lesya' in audio_path_str or ('uk' in audio_path_str and 'macos' in audio_path_str):
                quality -= 2.0  # Известные проблемы с украинским Lesya
            
            # Проверка соотношения длительности текста и аудио
            expected_duration = len(text) / 12.0  # примерно 12 символов в секунду
            duration_ratio = duration / expected_duration if expected_duration > 0 else 1.0
            
            if duration_ratio < 0.5 or duration_ratio > 2.0:
                quality -= 1.0  # Подозрительное соотношение
            
            return max(1.0, min(10.0, quality))
        
        except Exception as e:
            self.logger.debug(f"Ошибка оценки качества: {e}")
            return 5.0  # Средняя оценка по умолчанию
    
    def _create_summary(self, results: List[PerformanceResult], language: str) -> Dict:
        """Создание сводки результатов"""
        
        # Группируем результаты по движкам
        engine_results = {}
        for result in results:
            engine = result.engine
            if engine not in engine_results:
                engine_results[engine] = []
            engine_results[engine].append(result)
        
        summary = {
            'language': language,
            'total_tests': len(results),
            'engines_tested': len(engine_results),
            'engine_performance': {}
        }
        
        for engine, engine_results_list in engine_results.items():
            successful = [r for r in engine_results_list if r.success]
            failed = [r for r in engine_results_list if not r.success]
            
            if successful:
                avg_synthesis_time = sum(r.duration_seconds for r in successful) / len(successful)
                avg_audio_duration = sum(r.audio_duration_seconds for r in successful if r.audio_duration_seconds) / len([r for r in successful if r.audio_duration_seconds])
                avg_quality = sum(r.quality_score for r in successful if r.quality_score) / len([r for r in successful if r.quality_score])
                avg_file_size = sum(r.file_size_bytes for r in successful if r.file_size_bytes) / len([r for r in successful if r.file_size_bytes])
            else:
                avg_synthesis_time = 0
                avg_audio_duration = 0  
                avg_quality = 0
                avg_file_size = 0
            
            summary['engine_performance'][engine.value] = {
                'success_rate': len(successful) / len(engine_results_list) * 100,
                'avg_synthesis_time': avg_synthesis_time,
                'avg_audio_duration': avg_audio_duration,
                'avg_quality_score': avg_quality,
                'avg_file_size_kb': avg_file_size / 1024 if avg_file_size else 0,
                'total_tests': len(engine_results_list),
                'successful_tests': len(successful),
                'failed_tests': len(failed)
            }
        
        # Определяем лучший движок
        best_engine = None
        best_score = 0
        
        for engine_name, perf in summary['engine_performance'].items():
            # Комплексный скор: успешность * качество / время
            if perf['avg_synthesis_time'] > 0:
                score = (perf['success_rate'] / 100) * perf['avg_quality_score'] / perf['avg_synthesis_time']
            else:
                score = 0
            
            if score > best_score:
                best_score = score
                best_engine = engine_name
        
        summary['best_engine'] = best_engine
        summary['best_score'] = best_score
        
        return summary
    
    def _log_comparison_results(self, report: ComparisonReport):
        """Логирование результатов сравнения"""
        
        self.logger.info(f"📊 === ОТЧЕТ СРАВНЕНИЯ TTS ДЛЯ {report.language.upper()} ===")
        self.logger.info(f"📅 Время: {report.timestamp}")
        self.logger.info(f"🔬 Всего тестов: {report.summary['total_tests']}")
        self.logger.info(f"🎤 Движков протестировано: {report.summary['engines_tested']}")
        
        self.logger.info(f"\n🏆 ЛУЧШИЙ ДВИЖОК: {report.summary['best_engine']} (скор: {report.summary['best_score']:.3f})")
        
        self.logger.info(f"\n📈 ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ:")
        
        for engine_name, perf in report.summary['engine_performance'].items():
            self.logger.info(f"  🎯 {engine_name}:")
            self.logger.info(f"    ✅ Успешность: {perf['success_rate']:.1f}% ({perf['successful_tests']}/{perf['total_tests']})")
            self.logger.info(f"    ⏱️  Скорость синтеза: {perf['avg_synthesis_time']:.2f}с")
            self.logger.info(f"    🎵 Длительность аудио: {perf['avg_audio_duration']:.2f}с")
            self.logger.info(f"    ⭐ Качество: {perf['avg_quality_score']:.1f}/10")
            self.logger.info(f"    💾 Размер файла: {perf['avg_file_size_kb']:.1f}KB")
    
    def _log_language_comparison(self, reports: Dict[str, ComparisonReport]):
        """Логирование сравнения языков"""
        
        self.logger.info(f"\n🌍 === СРАВНЕНИЕ РУССКОГО И УКРАИНСКОГО TTS ===")
        
        ru_report = reports.get('ru')
        uk_report = reports.get('uk')
        
        if ru_report and uk_report:
            ru_best = ru_report.summary['best_engine']
            uk_best = uk_report.summary['best_engine']
            
            self.logger.info(f"🇷🇺 Лучший для русского: {ru_best}")
            self.logger.info(f"🇺🇦 Лучший для украинского: {uk_best}")
            
            # Сравнение производительности движков
            for engine_name in ['macos', 'google_tts']:
                ru_perf = ru_report.summary['engine_performance'].get(engine_name, {})
                uk_perf = uk_report.summary['engine_performance'].get(engine_name, {})
                
                if ru_perf and uk_perf:
                    self.logger.info(f"\n📊 {engine_name.upper()}:")
                    self.logger.info(f"  🇷🇺 RU: успешность {ru_perf.get('success_rate', 0):.1f}%, качество {ru_perf.get('avg_quality_score', 0):.1f}/10, время {ru_perf.get('avg_synthesis_time', 0):.2f}с")
                    self.logger.info(f"  🇺🇦 UK: успешность {uk_perf.get('success_rate', 0):.1f}%, качество {uk_perf.get('avg_quality_score', 0):.1f}/10, время {uk_perf.get('avg_synthesis_time', 0):.2f}с")
            
            # Рекомендации
            self.logger.info(f"\n💡 РЕКОМЕНДАЦИИ:")
            if ru_best == uk_best:
                self.logger.info(f"  ✅ Движок {ru_best} оптимален для обоих языков")
            else:
                self.logger.info(f"  ⚠️  Для русского лучше {ru_best}, для украинского - {uk_best}")
                self.logger.info(f"  🔄 Рекомендуется использовать разные движки для разных языков")
    
    def save_report_to_file(self, reports: Dict[str, ComparisonReport], filename: str = None):
        """Сохранение отчета в файл"""
        
        if not filename:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"tts_comparison_report_{timestamp}.json"
        
        report_path = self.config.LOGS_FOLDER / filename
        
        # Подготавливаем данные для JSON
        json_data = {}
        for lang, report in reports.items():
            json_data[lang] = {
                'language': report.language,
                'timestamp': report.timestamp,
                'test_texts': report.test_texts,
                'summary': report.summary,
                'results': [
                    {
                        'engine': r.engine.value,
                        'language': r.language,
                        'text': r.text,
                        'success': r.success,
                        'duration_seconds': r.duration_seconds,
                        'audio_duration_seconds': r.audio_duration_seconds,
                        'file_size_bytes': r.file_size_bytes,
                        'quality_score': r.quality_score,
                        'error_message': r.error_message
                    }
                    for r in report.results
                ]
            }
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"💾 Отчет сохранен: {report_path}")
            return str(report_path)
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения отчета: {e}")
            return None


if __name__ == "__main__":
    # Тестирование
    print("=== Тестирование TTSPerformanceTester ===")
    
    tester = TTSPerformanceTester()
    
    print("\n=== Быстрый тест одного движка ===")
    result = tester.test_engine_performance(TTSEngine.MACOS, 'ru', "Привет, это тест TTS")
    print(f"Результат: успех={result.success}, время={result.duration_seconds:.2f}с")
    
    print("\n=== Полное сравнение русского и украинского ===")
    reports = tester.compare_russian_vs_ukrainian()
    
    # Сохраняем отчет
    report_file = tester.save_report_to_file(reports)
    if report_file:
        print(f"📄 Отчет сохранен в: {report_file}")