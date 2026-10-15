Feature: Verktygen talar om vad de gör med brevlådan
  Som MCP-klient som frågar användaren innan riskabla åtgärder
  vill jag att varje verktyg är märkt med titel och annoteringar
  så att läsverktyg kan godkännas automatiskt medan radering och skick kräver godkännande.

  Scenario: Alla verktyg har titel och annoteringar
    When klienten listar verktygen
    Then ska varje verktyg ha en titel
    And ska varje verktyg ha annoteringar för läs-endast, destruktiv, idempotent och öppen värld

  Scenario Outline: Läsverktyg är märkta som läs-endast
    When klienten listar verktygen
    Then ska <verktyg> vara läs-endast
    And ska <verktyg> inte nå omvärlden

    Examples:
      | verktyg            |
      | list_mailboxes     |
      | get_mailbox_status |
      | list_emails        |
      | get_email          |
      | get_email_headers  |
      | search_emails      |
      | get_thread         |

  Scenario Outline: Verktyg som raderar, flyttar eller ersätter är destruktiva
    When klienten listar verktygen
    Then ska <verktyg> vara destruktivt

    Examples:
      | verktyg       |
      | delete_email  |
      | move_email    |
      | remove_label  |
      | delete_folder |
      | rename_folder |
      | update_draft  |

  Scenario Outline: Verktyg som skickar mejl till omvärlden är märkta som öppen värld
    When klienten listar verktygen
    Then ska <verktyg> nå omvärlden
    And ska <verktyg> vara destruktivt

    Examples:
      | verktyg        |
      | send_email     |
      | reply_to_email |
      | forward_email  |
      | send_draft     |

  Scenario Outline: Att sätta samma markering igen ändrar inget
    When klienten listar verktygen
    Then ska <verktyg> vara idempotent
    And ska <verktyg> inte vara destruktivt

    Examples:
      | verktyg           |
      | mark_email_read   |
      | mark_email_unread |
      | flag_email        |
      | unflag_email      |
      | add_label         |

  Scenario Outline: Utkast skapas utan att något skickas eller skrivs över
    When klienten listar verktygen
    Then ska <verktyg> inte vara destruktivt
    And ska <verktyg> inte nå omvärlden

    Examples:
      | verktyg              |
      | create_draft         |
      | create_reply_draft   |
      | create_forward_draft |
