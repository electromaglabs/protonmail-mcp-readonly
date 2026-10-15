Feature: Läsverktyg som tar ett UID kräver mappen som UID:t kom från
  Som modell som läser mejl med UID:n från get_thread, utkast och sökningar
  vill jag att get_email och get_email_headers kräver mailbox
  eftersom samma UID i INBOX är ett annat mejl, och ett tyst felaktigt mejl kan leda till svar till fel person.

  Scenario Outline: Ett läsverktyg utan mapp avvisas innan något läses
    When jag anropar <verktyg> med uid "70" utan mapp
    Then ska anropet avvisas för att mailbox saknas
    And ska inget mejl ha lästs

    Examples:
      | verktyg           |
      | get_email         |
      | get_email_headers |

  Scenario Outline: Ett läsverktyg med mappen från trådsvaret läser i den mappen
    Given att "All Mail" har mejlet med UID "70"
    When jag anropar <verktyg> med uid "70" i mappen "All Mail"
    Then ska mejlet med UID "70" ha lästs i "All Mail"

    Examples:
      | verktyg           |
      | get_email         |
      | get_email_headers |

  Scenario Outline: Beskrivningen säger att mailbox är obligatorisk och varför
    When jag läser schemat för <verktyg>
    Then ska mailbox vara obligatorisk utan standardvärde
    And ska beskrivningen säga att UID:t gäller per mapp

    Examples:
      | verktyg           |
      | get_email         |
      | get_email_headers |

  Scenario: Rubrikerna beskrivs som råa värden
    When jag läser schemat för get_email_headers
    Then ska beskrivningen säga att värdena är råa och att RFC 2047-kodade ord inte avkodas
    And ska beskrivningen säga att en rubrik som saknas inte finns med som nyckel
    And ska beskrivningen hänvisa till get_email för läsbar text
