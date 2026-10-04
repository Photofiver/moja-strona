# TikTok Trend Bot

Darmowy bot działający niezależnie od bota tradingowego.

Co godzinę:
1. sprawdza publiczny TikTok Creative Center,
2. próbuje pobrać najpopularniejszy trend wideo dla UK,
3. jeśli TikTok nie udostępni listy wideo, używa najpopularniejszego trendu/hashtagu z UK,
4. tworzy własny pionowy film 1080x1920 z polskim głosem AI,
5. publikuje gotowy plik MP4 jako asset GitHub Release,
6. wysyła alert przez GitHub Issue #1 z linkiem do filmu i gotowym opisem.

Bot nie kopiuje cudzych filmów i nie publikuje automatycznie na TikToku. Ostatnie zatwierdzenie/publikację wykonuje użytkownik.
