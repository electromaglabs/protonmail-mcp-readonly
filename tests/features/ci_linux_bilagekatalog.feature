Feature: Bilagekatalogen är lika svår att kapa på Linux som på macOS
  Som användare som kör servern på Linux (eller i CI)
  vill jag att samma skydd gäller som på macOS
  så att en fil inte kan bytas ut och en symlänk inte kan smita igenom bara för att filsystemet eller användaren är en annan.

  Background:
    Given en bilagekatalog med filen "offert.pdf"

  Scenario: En fil som byts mot en ny fil med samma inodnummer skickas inte
    Given att "offert.pdf" efter kontrollen byts mot en ny fil som återanvänder inodnumret
    When jag försöker skicka "offert.pdf" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "ändrades"
