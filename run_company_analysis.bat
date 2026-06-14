@echo off
REM Скрипт для анализа новостей на предмет упоминаний компаний и экспорта в Excel
REM Использование: run_company_analysis.bat [команда] [параметры]

echo ========================================
echo Анализатор новостей по компаниям
echo ========================================

REM Проверяем наличие Python
where py >nul 2>nul
if %errorlevel% neq 0 (
    echo Ошибка: Python не найден. Установите Python 3.8+ или используйте 'python' вместо 'py'
    pause
    exit /b 1
)

REM Если нет аргументов, показываем справку
if "%~1"=="" (
    echo Примеры использования:
    echo   run_company_analysis.bat parse -d 7 -l 100
    echo   run_company_analysis.bat analyze --export-excel
    echo   run_company_analysis.bat stats
    echo   run_company_analysis.bat export --format excel
    echo   run_company_analysis.bat search -c "Газпром"
    echo.
    echo Для подробной справки: run_company_analysis.bat help
    pause
    exit /b 0
)

if "%~1"=="help" (
    echo Полная справка по командам:
    echo.
    py cli.py --help
    pause
    exit /b 0
)

echo Запуск анализа...
echo.

REM Запускаем Python скрипт с переданными аргументами
py cli.py %*

if %errorlevel% equ 0 (
    echo.
    echo Операция успешно завершена!
) else (
    echo.
    echo Ошибка при выполнении операции
)

echo.
pause