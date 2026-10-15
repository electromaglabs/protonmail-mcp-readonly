Feature: Skickläge (PROTONMAIL_SEND_MODE)
  Som användare som låter en LLM hjälpa till med e-post
  vill jag kunna bestämma att den bara får skriva utkast, eller inte ens det,
  så att inget mejl går iväg utan att jag själv har granskat och skickat det.

  Scenario Outline: I läget draft_only vägras allt som skickar, med hänvisning till utkasten
    Given servern körs med inställningen "send_mode" satt till "draft_only"
    When LLM:en anropar verktyget "<verktyg>"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_SEND_MODE=draft_only"
    And ska felet hänvisa till "create_draft", "create_reply_draft" och "create_forward_draft"
    And ska Bridge inte ha kontaktats

    Examples:
      | verktyg        |
      | send_email     |
      | reply_to_email |
      | forward_email  |
      | send_draft     |

  Scenario: I läget draft_only får LLM:en skapa utkast
    Given servern körs med inställningen "send_mode" satt till "draft_only"
    And Bridge sparar utkast i Drafts med UID "12"
    When LLM:en anropar verktyget "create_draft"
    Then ska verktyget svara utan fel
    And ska utkastet ha sparats i Drafts

  Scenario: I läget draft_only vägrar SMTP-klienten även om ett verktyg skulle glömmas
    Given en SMTP-klient för ett konto med inställningen "send_mode" satt till "draft_only"
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_SEND_MODE=draft_only"
    And ska Bridge inte ha kontaktats

  Scenario Outline: I läget disabled vägras både skick och utkast
    Given servern körs med inställningen "send_mode" satt till "disabled"
    When LLM:en anropar verktyget "<verktyg>"
    Then ska anropet vägras med ett fel som nämner "PROTONMAIL_SEND_MODE=disabled"
    And ska Bridge inte ha kontaktats

    Examples:
      | verktyg              |
      | send_email           |
      | send_draft           |
      | create_draft         |
      | create_reply_draft   |
      | create_forward_draft |
      | update_draft         |

  Scenario: I läget disabled fungerar flytt och märkning som vanligt
    Given servern körs med inställningen "send_mode" satt till "disabled"
    When LLM:en anropar verktyget "move_email"
    Then ska anropet inte ha vägrats av skickläget

  Scenario: Standardläget skickar som förut
    Given en SMTP-klient för ett konto utan begränsningar
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se"
    Then ska mejlet ha skickats till "anna@exempel.se"
