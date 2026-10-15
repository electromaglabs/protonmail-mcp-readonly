Feature: Promptargument kan inte bära med sig radbrytningar
  Som användare som väljer en färdig prompt
  vill jag att mappnamn, UID och ton inte kan bryta raden i instruktionen
  eftersom ett argument som ser ut som en egen rad kan läsas som en ny instruktion
  till modellen (t.ex. "Skicka med send_email").

  Scenario Outline: Unicode-radbrytningar och C1-kontrolltecken i tonen vägras
    When klienten hämtar prompten "svara_pa_mejl" med en ton som innehåller tecknet <tecken>
    Then ska hämtningen misslyckas med texten "ton får inte innehålla radbrytningar"

    Examples:
      | tecken |
      | U+2028 |
      | U+2029 |
      | U+0085 |
      | U+0080 |
      | U+009F |

  Scenario Outline: Unicode-radbrytningar och C1-kontrolltecken i mappnamnet vägras
    When klienten hämtar prompten "<prompt>" med ett mappnamn som innehåller tecknet <tecken>
    Then ska hämtningen misslyckas med texten "mailbox får inte innehålla radbrytningar"

    Examples:
      | prompt             | tecken |
      | sammanfatta_olasta | U+2028 |
      | triagera_inkorgen  | U+2029 |
      | rensa_nyhetsbrev   | U+0085 |
      | svara_pa_mejl      | U+009B |

  Scenario: Ett UID med en Unicode-radbrytning vägras
    When klienten hämtar prompten "svara_pa_mejl" med ett UID som innehåller tecknet U+2028
    Then ska hämtningen misslyckas med texten "UID"

  Scenario: Vanliga mappnamn och toner fungerar som förut
    When klienten hämtar prompten "svara_pa_mejl" med mappnamnet "Labels/Näs Samfällighet" och tonen "vänlig – kort"
    Then ska prompttexten nämna "Labels/Näs Samfällighet"
    And ska prompttexten nämna "vänlig – kort"
