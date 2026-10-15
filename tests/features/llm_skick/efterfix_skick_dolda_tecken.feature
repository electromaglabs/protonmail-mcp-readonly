Feature: Mottagaradresser med dolda tecken vägras i alla skick- och utkastvägar
  Som användare som granskar vem ett mejl går till
  vill jag att en adress med osynliga tecken (taggtecken, bidi-styrtecken,
  nollbreddstecken och andra formattecken) aldrig blir en mottagare
  så att mejlet inte går till en annan brevlåda än den jag ser.
  ([U+XXXX] i adresserna står för det osynliga tecknet med den kodpunkten.)

  Scenario Outline: send_email vägrar en adress med dolda tecken
    Given en SMTP-klient för ett konto utan begränsningar
    When LLM:en skickar ett mejl till adressen "<adress>"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget mejl ha skickats

    Examples:
      | adress                          |
      | boss[U+E0041][U+E0042]@company.com |
      | b‮oss@company.com          |
      | boss​@company.com          |
      | boss­@company.com          |
      | boss⁦@company.com          |

  Scenario: Svar till en Reply-To med taggtecken vägras
    Given INBOX har ett mejl med UID "5" med svarsadressen "boss[U+E0041][U+E0042]@company.com"
    When LLM:en svarar på UID "5" i "INBOX"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget mejl ha skickats

  Scenario: Svarsutkast till en Reply-To med taggtecken sparas inte
    Given INBOX har ett mejl med UID "5" med svarsadressen "boss[U+E0041][U+E0042]@company.com"
    When LLM:en skapar ett svarsutkast till UID "5" i "INBOX"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget utkast ha sparats

  Scenario: Vidarebefordran till en adress med bidi-styrtecken vägras
    Given INBOX har ett mejl med UID "5" med svarsadressen "kund@exempel.se"
    When LLM:en vidarebefordrar UID "5" i "INBOX" till adressen "b‮oss@company.com"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget mejl ha skickats

  Scenario: Ett utkast med en dold mottagare skickas inte med send_draft
    Given Drafts har ett utkast med UID "7" till "boss​@company.com"
    When LLM:en skickar utkastet med UID "7"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget mejl ha skickats

  Scenario: create_draft vägrar en hemlig kopia med dolda tecken
    Given en SMTP-klient för ett konto utan begränsningar
    When LLM:en skapar ett utkast till "anna@exempel.se" med hemlig kopia till adressen "spion[U+E0041]@ond.example"
    Then ska anropet vägras med ett fel som nämner "dolda tecken"
    And ska inget utkast ha sparats
