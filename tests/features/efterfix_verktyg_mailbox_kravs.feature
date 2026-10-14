Feature: Skrivverktyg kräver mappen som UID:t kom från
  Som en MCP-klient
  vill jag att verktyg som ändrar brev kräver att jag anger mapp
  eftersom ett UID bara gäller i sin mapp och samma nummer i INBOX är ett annat brev.

  Scenario Outline: Ett skrivverktyg utan mapp avvisas innan något ändras
    Given att INBOX har ett annat brev med UID "14"
    When jag anropar <verktyg> med uid "14" utan mapp
    Then ska anropet avvisas för att mailbox saknas
    And ska inget brev ha ändrats

    Examples:
      | verktyg           |
      | delete_email      |
      | move_email        |
      | mark_email_read   |
      | mark_email_unread |

  Scenario Outline: Ett skrivverktyg med mappen från listningen påverkar brevet i den mappen
    Given att INBOX har ett annat brev med UID "14"
    When jag anropar <verktyg> med uid "14" i mappen "Labels/Kvitto"
    Then ska ändringen gälla brevet med UID "14" i "Labels/Kvitto"

    Examples:
      | verktyg           |
      | move_email        |
      | mark_email_read   |
      | mark_email_unread |

  Scenario Outline: Verktygsbeskrivningen säger att mailbox är obligatorisk och varför
    When jag läser verktygsbeskrivningen för <verktyg>
    Then ska mailbox vara obligatorisk utan standardvärde
    And ska beskrivningen säga att UID:t gäller per mapp

    Examples:
      | verktyg           |
      | delete_email      |
      | move_email        |
      | mark_email_read   |
      | mark_email_unread |

  Scenario Outline: Läsverktyg har fortfarande INBOX som standard
    When jag läser verktygsbeskrivningen för <verktyg>
    Then ska mailbox ha standardvärdet "INBOX"

    Examples:
      | verktyg           |
      | get_email         |
      | get_email_headers |
      | list_emails       |
      | search_emails     |
