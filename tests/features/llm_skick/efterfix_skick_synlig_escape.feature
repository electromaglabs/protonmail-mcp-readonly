Feature: En adress med den synliga märkningen av ett dolt tecken vägras begripligt
  Som användare vars mejlvisning skriver dolda tecken i adresser som "[U+E0041]"
  vill jag att en LLM som kopierar en sådan visad adress får ett begripligt fel
  i stället för att mejlet skickas till en annan adress.
  (Adresserna i det här scenariot står exakt som de skickas, med hakparenteserna.)

  Scenario: send_email till en kopierad adress med "[U+" vägras
    Given en SMTP-klient för ett konto utan begränsningar
    When LLM:en skickar ett mejl till den kopierade adressen "boss[U+E0041]@company.com"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska felet nämna "[U+"
    And ska inget mejl ha skickats

  Scenario: Ett svar med en kopierad adress i kopia vägras
    Given INBOX har ett vanligt mejl med UID "5" från "kund@exempel.se"
    When LLM:en svarar på UID "5" i "INBOX" med kopia till den kopierade adressen "boss[u+e0041]@company.com"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget mejl ha skickats

  Scenario: Ett utkast till en kopierad adress sparas inte
    Given en SMTP-klient för ett konto utan begränsningar
    When LLM:en skapar ett utkast till den kopierade adressen "boss[U+202E]@company.com"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget utkast ha sparats

  Scenario: Ett utkast vars mottagare har den synliga märkningen skickas inte
    Given Drafts har ett utkast med UID "7" till den kopierade adressen "boss[U+E0041]@company.com"
    When LLM:en skickar utkastet med UID "7"
    Then ska anropet vägras med ett fel som nämner "Ogiltig e-postadress"
    And ska inget mejl ha skickats

  Scenario: Svar till ett original vars Reply-To har råa taggtecken vägras
    Given INBOX har ett mejl med UID "5" med svarsadressen "boss[U+E0041]@company.com"
    When LLM:en svarar på UID "5" i "INBOX"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget mejl ha skickats
