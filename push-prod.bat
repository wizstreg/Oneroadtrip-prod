@echo off
echo ================================================================
echo                    ONE ROAD TRIP - PUSH PROD
echo ================================================================
echo.

echo [1/3] Verification et scraping des hotels manquants...
echo ----------------------------------------------------------------
node "C:\OneRoadTrip\data\Roadtripsprefabriques\tools\script\check-and-scrape-hotels.js"

echo.
echo [DEBUG] Script check-and-scrape termine
pause

if errorlevel 1 (
    echo.
    echo [ERREUR] Probleme lors du traitement des hotels
    pause
    exit /b 1
)

echo.
echo [2/3] Decoupe des hotels par pays/initiale...
echo ----------------------------------------------------------------
node "C:\OneRoadTrip\data\Roadtripsprefabriques\tools\script\divide-hotels.js"

echo.
echo [DEBUG] Script divide-hotels termine
pause

if errorlevel 1 (
    echo.
    echo [ERREUR] Probleme lors du decoupe des hotels
    pause
    exit /b 1
)

echo.
echo [3/3] Push vers les 3 repositories...
echo ----------------------------------------------------------------

echo.
echo --- OneRoadTrip ---
cd /d "C:\OneRoadTrip"
git add .
git commit -m "update %date% %time%"
git push
if errorlevel 1 (
    echo [WARN] Erreur push OneRoadTrip
)

echo.
echo --- Ort prod ---
cd /d "C:\Ort prod"
git add .
git commit -m "update %date% %time%"
git push
if errorlevel 1 (
    echo [WARN] Erreur push Ort prod
)

echo.
echo --- Ort test ---
cd /d "C:\Ort test"
git add .
git commit -m "update %date% %time%"
git push
if errorlevel 1 (
    echo [WARN] Erreur push Ort test
)

echo.
echo ================================================================
echo                         TERMINE !
echo ================================================================
pause
