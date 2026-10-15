Feature: Samma mottagare får mejlet en gång, och gränsen räknar det som skickas
  Som användare som har begränsat antalet mottagare per mejl
  vill jag att gränsen räknar exakt de mottagare som Bridge får
  så att en LLM inte kan skicka samma mejl många gånger genom att upprepa en adress.

  Scenario: Upprepade adresser och skiftlägesvarianter blir en enda mottagare
    Given en SMTP-klient för ett konto med inställningen "max_recipients" satt till "1"
    When koden direkt i SMTP-klienten skickar ett mejl till adresserna "victim@x.se, victim@x.se, Victim@x.se, VICTIM@X.SE, vIcTiM@x.se"
    Then ska mejlet ha skickats till "victim@x.se"

  Scenario: En adress i både To och Bcc får mejlet en gång
    Given en SMTP-klient för ett konto utan begränsningar
    When koden direkt i SMTP-klienten skickar ett mejl till adresserna "anna@exempel.se, bo@exempel.se" med hemlig kopia till "ANNA@exempel.se"
    Then ska mejlet ha skickats till "anna@exempel.se, bo@exempel.se"

  Scenario: Olika adresser räknas fortfarande var för sig
    Given en SMTP-klient för ett konto med inställningen "max_recipients" satt till "1"
    When koden direkt i SMTP-klienten skickar ett mejl till adresserna "anna@exempel.se, bo@exempel.se, anna@exempel.se"
    Then ska anropet vägras med ett fel som nämner "2 mottagare"
    And ska Bridge inte ha kontaktats

  Scenario: En orimligt lång mottagarlista vägras innan den bearbetas, även utan gräns
    Given en SMTP-klient för ett konto med inställningen "max_recipients" satt till "0"
    When koden direkt i SMTP-klienten skickar ett mejl till 5000 adresser
    Then ska anropet vägras med ett fel som nämner "för många adresser"
    And ska Bridge inte ha kontaktats
