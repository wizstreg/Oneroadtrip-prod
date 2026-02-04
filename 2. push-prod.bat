@echo off
cd /d "C:\Ort prod"
git add .
git commit -m "update %date% %time%"
git push
pause