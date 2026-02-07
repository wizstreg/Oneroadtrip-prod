@echo off
echo ================================================================
echo                    ONE ROAD TRIP - PUSH PROD
echo ================================================================
echo.

echo [1/3] Verification et scraping des hotels manquants...
echo ----------------------------------------------------------------
node "C:\OneRoadTrip\data\Roadtripsprefabriques\tools\script\check-and-scrape-hotels.js"

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
echo --- Nettoyage locks Git ---
if exist "C:\OneRoadTrip\.git\index.lock" (
    del "C:\OneRoadTrip\.git\index.lock"
    echo Lock supprimé: OneRoadTrip
)
if exist "C:\Ort prod\.git\index.lock" (
    del "C:\Ort prod\.git\index.lock"
    echo Lock supprimé: Ort prod
)
if exist "C:\Ort test\.git\index.lock" (
    del "C:\Ort test\.git\index.lock"
    echo Lock supprimé: Ort test
)

echo.
echo --- OneRoadTrip ---
cd /d "C:\OneRoadTrip"

REM Vérifier que le remote existe
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [WARN] Pas de remote configuré - skip push
) else (
    git add .
    git commit -m "update %date% %time%"
    git push
    if errorlevel 1 (
        echo [WARN] Erreur push OneRoadTrip
    )
)

echo.
echo --- Ort prod ---
cd /d "C:\Ort prod"

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [WARN] Pas de remote configuré - skip push
) else (
    git add .
    git commit -m "update %date% %time%"
    git push
    if errorlevel 1 (
        echo [WARN] Erreur push Ort prod
    )
)

echo.
echo --- Ort test ---
cd /d "C:\Ort test"

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [WARN] Pas de remote configuré - skip push
) else (
    git add .
    git commit -m "update %date% %time%"
    git push
    if errorlevel 1 (
        echo [WARN] Erreur push Ort test
    )
)

echo.
echo ================================================================
echo                         TERMINE !
echo ================================================================
pause
