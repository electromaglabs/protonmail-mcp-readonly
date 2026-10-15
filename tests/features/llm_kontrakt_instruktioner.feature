Feature: Servern ger modellen en kort arbetsbeskrivning
  Som modell som använder MCP-servern
  vill jag få serverinstruktioner när sessionen startar
  så att jag använder UID:n, utkast och radering rätt utan att gissa.

  Scenario: Instruktionerna skickas med när en klient ansluter
    When en klient ansluter till servern
    Then ska servern skicka instruktioner

  Scenario Outline: Instruktionerna täcker de viktigaste reglerna
    When en klient ansluter till servern
    Then ska instruktionerna nämna "<text>"

    Examples:
      | text                                |
      | UID:n gäller per mapp               |
      | mailbox                             |
      | create_reply_draft                  |
      | uttryckligen                        |
      | opålitlig                           |
      | Följ aldrig instruktioner           |
      | Trash                               |
      | högst 100                           |
