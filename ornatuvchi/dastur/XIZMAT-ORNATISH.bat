@echo off
title NigohAI - doimiy ishlash rejimi
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo   Administrator huquqi kerak - ruxsat oynasida "Ha" bosing...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0xizmat.ps1"
