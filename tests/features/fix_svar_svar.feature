Feature: Svara på e-post
  Som en MCP-klient som svarar på mejl
  vill jag att svaret får rätt ämne, trådning och mottagare
  så att det hamnar rätt och hänger ihop med konversationen hos mottagaren.

  Scenario Outline: Lokaliserade svarsprefix ger ett enda "Re: "
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "10" från "anna@example.se" med ämnet "<ämne>"
    When jag svarar på mejlet med UID "10" med texten "Tack!"
    Then ska svarets ämne vara "<svarsämne>"

    Examples:
      | ämne                  | svarsämne    |
      | möte                  | Re: möte     |
      | Re: möte              | Re: möte     |
      | SV: möte              | Re: möte     |
      | SV: Re: SV: möte      | Re: möte     |
      | AW: Antw: VS: möte    | Re: möte     |
      | RE[2]: möte           | Re: möte     |
      | Fwd: Fw: VB: möte     | Re: möte     |
      | Svar på frågan        | Re: Svar på frågan |
      | =?utf-8?q?SV=3A_m=C3=B6te?= | Re: möte |
