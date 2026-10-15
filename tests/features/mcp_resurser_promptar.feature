Feature: Färdiga promptar för vanliga mejlsysslor
  Som användare i en MCP-klient
  vill jag kunna välja en färdig prompt (sammanfatta, triagera, svara, rensa nyhetsbrev)
  som instruerar modellen att använda verktygen säkert
  så att den inte skickar, raderar eller följer instruktioner i mejl utan att jag bett om det.

  Scenario: Promptarna listas med sina argument
    When klienten listar promptarna
    Then ska prompten "sammanfatta_olasta" finnas med argumenten "mailbox, max_antal"
    And ska prompten "triagera_inkorgen" finnas med argumenten "mailbox"
    And ska prompten "svara_pa_mejl" finnas med argumenten "uid, mailbox, ton"
    And ska prompten "rensa_nyhetsbrev" finnas med argumenten "mailbox"
    And ska argumenten "uid" och "mailbox" vara obligatoriska för "svara_pa_mejl"

  Scenario Outline: Varje prompt påminner om säkerhetsreglerna
    When klienten hämtar prompten "<prompt>" med <argument>
    Then ska prompttexten vara på svenska
    And ska prompttexten säga att UID:n gäller per mapp
    And ska prompttexten säga att mejlinnehåll är opålitligt
    And ska prompttexten säga högst 100 per massoperation

    Examples:
      | prompt             | argument                    |
      | sammanfatta_olasta | inga argument               |
      | triagera_inkorgen  | inga argument               |
      | svara_pa_mejl      | uid "42" och mailbox "INBOX" |
      | rensa_nyhetsbrev   | inga argument               |

  Scenario: Sammanfatta olästa i en viss mapp
    When klienten hämtar prompten "sammanfatta_olasta" med mailbox "Labels/Näs Samfällighet" och max_antal "5"
    Then ska prompttexten nämna "Labels/Näs Samfällighet"
    And ska prompttexten nämna "5"
    And ska prompttexten nämna "search_emails"
    And ska prompttexten säga att inget ska markeras som läst

  Scenario: Triagering utför inget destruktivt utan bekräftelse
    When klienten hämtar prompten "triagera_inkorgen" med inga argument
    Then ska prompttexten nämna "INBOX"
    And ska prompttexten kräva bekräftelse från användaren innan något flyttas eller raderas

  Scenario: Svar blir ett utkast som inte skickas
    When klienten hämtar prompten "svara_pa_mejl" med uid "42", mailbox "Folders/Kunder" och ton "formell"
    Then ska prompttexten nämna "create_reply_draft"
    And ska prompttexten nämna "get_thread"
    And ska prompttexten nämna "formell"
    And ska prompttexten nämna "UID 42"
    And ska prompttexten nämna "Folders/Kunder"
    And ska prompttexten säga att svaret inte ska skickas

  Scenario: Rensa nyhetsbrev med List-Unsubscribe och bekräftelse
    When klienten hämtar prompten "rensa_nyhetsbrev" med inga argument
    Then ska prompttexten nämna "List-Unsubscribe"
    And ska prompttexten kräva bekräftelse från användaren innan något flyttas eller raderas

  Scenario Outline: Ogiltiga argument vägras
    When klienten hämtar prompten "svara_pa_mejl" med uid "<uid>" och mailbox "<mailbox>"
    Then ska hämtningen misslyckas med texten "<fel>"

    Examples:
      | uid  | mailbox | fel           |
      | 1:*  | INBOX   | Ogiltigt UID  |
      | abc  | INBOX   | Ogiltigt UID  |
      | 42   |         | mailbox       |

  Scenario: För många mejl att sammanfatta vägras
    When klienten hämtar prompten "sammanfatta_olasta" med mailbox "INBOX" och max_antal "500"
    Then ska hämtningen misslyckas med texten "max_antal"
