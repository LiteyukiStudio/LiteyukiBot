from nonebot import on_command
from extraApi.base import Command
from extraApi.rule import *

dna_comp = on_command(cmd="dna互补", aliases={"DNA互补"},
                      rule=plugin_enable("kami.learning_tools") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                      priority=10, block=True)
dna_translation = on_command(cmd="dna翻译", aliases={"DNA翻译"},
                             rule=plugin_enable("kami.learning_tools") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                             priority=10, block=True)


@dna_comp.handle()
async def dna_comp_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    comp_dict = {
        "a": "T",
        "t": "A",
        "c": "G",
        "g": "C",
        "u": "A",
        "A": "T",
        "T": "A",
        "C": "G",
        "G": "C",
        "U": "A"
    }

    args, kws = Command.formatToCommand(cmd=event.raw_message)

    raw_chain = args[1]
    if raw_chain[0] == "3":
        pass
    else:
        raw_chain = raw_chain[::-1]

    comp_chain = ""
    for char in raw_chain:
        comp_chain += comp_dict.get(char, "X")
    comp_chain = "5'" + comp_chain + "3'"
    await dna_comp.send(message=comp_chain)


@dna_translation.handle()
async def dna_translation_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    codon_table = {
        "Phe": ["TTT", "TTC"],
        "Leu": ["TTA", "TTG", "CTT", "CTC", "CTA", "CTG"],
        "Ile": ["ATT", "ATA", "ATC"],
        "Met": ["ATG"],
        "Val": ["GTT", "GTC", "GTA", "GTG"],
        "Ser": ["TCT", "TCC", "TCA", "TCG", "AGT", "AGC"],
        "Pro": ["CCT", "CCC", "CCA", "CCG"],
        "Thr": ["ACT", "ACC", "ACA", "ACG"],
        "Ala": ["GCT", "GCC", "GCA", "GCG"],
        "Tyr": ["TAT", "TAC"],
        "赭石": ["TAA"],
        "琥珀": ["TAG"],
        "His": ["CAT", "CAC"],
        "Gln": ["CAA", "CAG"],
        "Asn": ["AAT", "AAC"],
        "Lys": ["AAA", "AAG"],
        "Asp": ["GAT", "GAC"],
        "Glu": ["GAA", "GAG"],

        "Cys": ["TGT", "TGC"],
        "蛋白石": ["TGA"],
        "Trp": ["TGG"],
        "Arg": ["CGT", "CGC", "CGA", "CGG", "AGA", "AGG"],
        "Gly": ["GGT", "GGC", "GGA", "GGG"]

    }
    args, kws = Command.formatToCommand(cmd=event.raw_message)

    raw_chain: str = args[1]
    if raw_chain[0] != "3":
        pass
    else:
        raw_chain = raw_chain[::-1]
    raw_chain = raw_chain.upper().replace("U", "T")

    s = ""
    ajs_list = []
    for c in raw_chain:
        s += c
        if len(s) == 3:
            ajs_list.append(s)
            s = ""

    tai = ""
    for ajs in ajs_list:
        for k, v in zip(codon_table.keys(), codon_table.values()):
            if ajs in v:
                tai += k + "-"

    await dna_translation.send(message=tai[:-1])
