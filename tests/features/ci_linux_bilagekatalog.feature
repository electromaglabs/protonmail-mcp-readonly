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

  Scenario: Som root räknas ingen symlänk som systemets egen
    Given att servern körs som root
    And att bilagekatalogen nås via symlänken "via" som ägs av root
    When jag försöker skicka "offert.pdf" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "symlänk"

  Scenario: En root-ägd symlänk i en katalog som andra kan skriva i avvisas
    Given att bilagekatalogen nås via symlänken "delad/via" som ägs av root
    And att katalogen "delad" har rättigheterna 777
    When jag försöker skicka "offert.pdf" som bilaga
    Then ska sändningen avvisas med ett fel som nämner "symlänk"

  Scenario: Systemets egna symlänkar, som /var på macOS, fungerar fortfarande
    Given att servern inte körs som root
    And att bilagekatalogen nås via symlänken "system/via" som ägs av root
    When jag försöker skicka "offert.pdf" som bilaga
    Then ska en bilaga med namnet "offert.pdf" ha byggts
