Feature: Datum i ISO 8601 bredvid det råa datumet
  Som användare av en LLM som läser min e-post
  vill jag att varje mejl har datumet i ISO 8601
  så att modellen kan jämföra och sortera datum utan att tolka RFC 5322-format.

  Scenario Outline: get_email ger date_iso
    Given ett mejl med datumet "<datum>"
    When jag hämtar mejlet med get_email
    Then ska date_iso vara "<iso>"

    Examples:
      | datum                                  | iso                       |
      | Tue, 14 Oct 2026 21:45:52 +0200        | 2026-10-14T21:45:52+02:00 |
      | Tue, 14 Oct 2026 21:45:52 +0200 (CEST) | 2026-10-14T21:45:52+02:00 |
      | 14 Oct 2026 19:45:52 GMT               | 2026-10-14T19:45:52+00:00 |
      | Tue, 14 Oct 2026 19:45:52 -0000        | 2026-10-14T19:45:52+00:00 |
      | Wed, 1 Jan 26 08:00:00 -0500           | 2026-01-01T08:00:00-05:00 |

  Scenario: Ett datum som inte går att tolka ger null
    Given ett mejl med datumet "imorgon någon gång"
    When jag hämtar mejlet med get_email
    Then ska date_iso vara null
    And det råa datumet ska vara "imorgon någon gång"

  Scenario: Listningen ger date_iso
    Given en IMAP-sida med ett mejl daterat "Tue, 14 Oct 2026 21:45:52 +0200"
    When sidans metadata parsas
    Then ska listningens date_iso vara "2026-10-14T21:45:52+02:00"
