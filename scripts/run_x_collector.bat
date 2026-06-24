@echo off
REM ============================================================
REM  Web Jornal Vale da Liberdade — Coletor do X (Twitter)
REM  Wrapper para Task Scheduler do Windows
REM  
REM  Como agendar:
REM    1. Abra o Task Scheduler (taskschd.msc)
REM    2. Crie uma nova tarefa
REM    3. Trigger: diário, repetir a cada 6 horas
REM    4. Action: executar este .bat
REM    5. Opcionalmente, adicione random delay de 30min
REM ============================================================

cd /d "j:\Arquivos Osmar\Hermes\web-jornal-vale-da-liberdade"

REM Criar diretório de logs se não existir
if not exist "logs" mkdir logs

REM Adicionar jitter aleatório de 0-15 minutos para parecer mais humano
set /a "JITTER=%RANDOM% %% 900"
echo [%date% %time%] Aguardando jitter de %JITTER% segundos... >> logs\x_collector.log
timeout /t %JITTER% /nobreak > nul

REM Executar coletor
echo [%date% %time%] Iniciando coleta do X... >> logs\x_collector.log
python scripts\x_collector.py --mode full >> logs\x_collector.log 2>&1
echo [%date% %time%] Coleta finalizada (exit code: %ERRORLEVEL%) >> logs\x_collector.log
echo. >> logs\x_collector.log
